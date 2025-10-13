from __future__ import annotations

import json
from typing import Dict, List, Tuple

from langchain.agents import AgentType, initialize_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.features.infra.browser_tool import get_browser_tool
from app.features.infra.sandbox_tool import get_sandbox_tool
from app.features.search.google_tool import get_google_search_tool
from app.logging import get_logger
from app.settings import get_settings

logger = get_logger()
settings = get_settings()

THREAD_MODEL_OVERRIDES: Dict[str, str] = {}


def _summarize_tool_output(raw: str) -> str:
    """Преобразует JSON или текст из инструмента в короткий человеческий ответ."""
    raw = (raw or "").strip()
    if not raw:
        return "Пустой результат."

    if not (raw.startswith("{") or raw.startswith("[")):
        return raw

    try:
        data = json.loads(raw)
    except Exception:
        return raw

    results = data.get("results") or []
    if isinstance(results, list) and results:
        snippets: List[str] = []
        for item in results[:2]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            snippet = (item.get("snippet") or "").strip()
            link = (item.get("link") or "").strip()
            if title or snippet:
                text_piece = f"{title}: {snippet}".strip(": ").strip()
                if link:
                    text_piece += f"\nИсточник: {link}"
                snippets.append(text_piece)
        if snippets:
            return "\n\n".join(snippets)

    return str(data)


def _build_conversation(
    prompt: str | None,
    history: list | None,
    messages: list[dict[str, str]] | None,
) -> List[Tuple[str, str]]:
    conversation: List[Tuple[str, str]] = []

    if messages:
        for entry in messages:
            role = entry.get("role") if isinstance(entry, dict) else None
            content = entry.get("content") if isinstance(entry, dict) else None
            if content is None or role is None:
                logger.warning(f"[AI QUERY] Пропущено сообщение без role/content: {entry}")
                continue

            if role == "system":
                conversation.append(("system", content))
            elif role == "user":
                conversation.append(("human", content))
            elif role == "assistant":
                conversation.append(("ai", content))
            else:
                logger.warning(f"[AI QUERY] Неизвестная роль сообщения: {role}")
    else:
        conversation.append(("system", "You are a helpful AI assistant."))
        if history:
            for msg in history:
                role = "human" if msg["type"] == "user" else "ai"
                conversation.append((role, msg["content"]))
        if prompt is not None:
            conversation.append(("human", prompt))

    return conversation


def _to_langchain_messages(conversation: List[Tuple[str, str]], prompt: str | None):
    lc_messages = []
    for role, content in conversation:
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "human":
            lc_messages.append(HumanMessage(content=content))
        elif role == "ai":
            lc_messages.append(AIMessage(content=content))
    if not lc_messages or not isinstance(lc_messages[-1], HumanMessage):
        final_content = prompt or (conversation[-1][1] if conversation else "")
        lc_messages.append(HumanMessage(content=final_content))
    return lc_messages


def _build_fallback_prompt(conversation: List[Tuple[str, str]]) -> str:
    parts: List[str] = []
    for role, content in conversation:
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "human":
            parts.append(f"User: {content}")
        elif role == "ai":
            parts.append(f"Assistant: {content}")
    return "\n".join(parts) if parts else ""


def call_ai_query(
    prompt: str | None = None,
    history: list | None = None,
    user_api_key: str | None = None,
    user_model: str | None = None,
    messages: list[dict[str, str]] | None = None,
    thread_id: str | None = None,
) -> str:
    model_override = THREAD_MODEL_OVERRIDES.get(thread_id) if thread_id else None
    actual_model = user_model or model_override or settings.openrouter_model
    actual_api_key = user_api_key or settings.openrouter_api_key

    logger.debug(f"[AI QUERY] prompt={prompt}")
    logger.debug(f"[AI QUERY] history={history}")
    logger.debug(f"[AI QUERY] incoming_messages={messages}")
    logger.debug(f"[AI QUERY] actual_model={actual_model}")
    logger.debug(f"[AI QUERY] actual_api_key={'***masked***' if actual_api_key else None}")

    if not actual_api_key:
        raise RuntimeError("Нет доступного OpenRouter API ключа")

    google_tool = get_google_search_tool()
    google_tool.name = "_execute"
    tools = [
        google_tool,
        get_browser_tool(),
        get_sandbox_tool(),
    ]
    tool_registry = {tool.name: tool for tool in tools}

    conversation = _build_conversation(prompt, history, messages)
    if not conversation:
        raise RuntimeError("Не удалось сформировать сообщения для модели")

    llm = ChatOpenAI(
        model=actual_model,
        temperature=0.6,
        openai_api_key=actual_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        max_tokens=settings.max_completion_tokens,
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "IgorekChatBot",
        },
    )

    lc_messages = _to_langchain_messages(conversation, prompt)

    try:
        llm_with_tools = llm.bind_tools(tools)
        result = llm_with_tools.invoke(lc_messages)
        logger.debug(f"[AI QUERY] Результат через tools API: {result}")

        tool_calls = result.additional_kwargs.get("tool_calls") if hasattr(result, "additional_kwargs") else None
        if tool_calls:
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                name = function.get("name")
                arguments = function.get("arguments", {})
                try:
                    parsed_args = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError:
                    parsed_args = {"input": arguments}
                if not isinstance(parsed_args, dict):
                    parsed_args = {"input": parsed_args}

                tool = tool_registry.get(name)
                if not tool:
                    logger.warning(f"[TOOL CALL] Неизвестный инструмент: {name}")
                    continue

                if name == "_execute":
                    prepared_args = parsed_args if isinstance(parsed_args, dict) else {"query": parsed_args}
                    if thread_id and isinstance(prepared_args, dict) and "thread_id" not in prepared_args:
                        prepared_args["thread_id"] = thread_id
                    raw_output = tool.run(prepared_args)
                    summary = _summarize_tool_output(raw_output)

                    prompt_for_llm = (
                        "Сформулируй краткий и понятный ответ на русском языке на основе этих данных."
                        " Не используй JSON, списки и лишние кавычки.\n\n"
                        f"{summary}"
                    )
                    try:
                        response_message = llm.invoke([HumanMessage(content=prompt_for_llm)])
                        answer = (
                            response_message.content.strip()
                            if hasattr(response_message, "content") and response_message.content
                            else str(response_message).strip()
                        )
                        if not answer:
                            answer = summary
                    except Exception as inner_exc:  # pragma: no cover
                        logger.warning(
                            "[TOOL RESPONSE] Не удалось переформулировать ответ: %s", inner_exc
                        )
                        answer = summary

                    logger.info("[TOOL RESPONSE] Ответ пользователю: %s", (answer or "")[:200])
                    return answer

                tool_result = tool.invoke(parsed_args)
                logger.info("[TOOL CALL] %s executed args=%s", name, parsed_args)

                prompt_for_llm = (
                    "Сформулируй краткий и понятный ответ на русском языке на основе этих данных."
                    " Не используй JSON, списки и лишние кавычки.\n\n"
                    f"{tool_result}"
                )
                try:
                    response_message = llm.invoke([HumanMessage(content=prompt_for_llm)])
                    answer = (
                        response_message.content.strip()
                        if hasattr(response_message, "content") and response_message.content
                        else str(response_message).strip()
                    )
                    if not answer:
                        answer = str(tool_result)
                except Exception as inner_exc:  # pragma: no cover
                    logger.warning(
                        "[TOOL RESPONSE] Не удалось переформулировать ответ для %s: %s",
                        name,
                        inner_exc,
                    )
                    answer = str(tool_result)

                logger.info("[TOOL RESPONSE] Ответ пользователю: %s", (answer or "")[:200])
                return answer

    except Exception as exc:  # pragma: no cover
        logger.warning(f"[AI QUERY] bind_tools недоступен, переход к fallback: {exc}")
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
        )
        fallback_prompt = _build_fallback_prompt(conversation)
        result = agent.invoke({"input": fallback_prompt or (prompt or "")})
        logger.debug(f"[AI QUERY] Результат fallback агента: {result}")

    final_text: str
    if hasattr(result, "content"):
        final_text = str(result.content)
    elif isinstance(result, dict):
        output = result.get("output") or result.get("text")
        final_text = str(output) if output is not None else str(result)
    else:
        final_text = str(result)

    final_text = (final_text or "").strip()
    if final_text.startswith("{") or final_text.startswith("["):
        final_text = _summarize_tool_output(final_text)

    return final_text
