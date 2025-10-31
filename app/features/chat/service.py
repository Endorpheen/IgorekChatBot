from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI

from app.features.chat.attachments import clear_thread_attachments, create_chat_attachment_tool
from app.features.infra.browser_tool import browse_website
from app.features.infra.sandbox_tool import run_code_in_sandbox
from app.features.search.google_tool import get_google_search_tool
from app.logging import get_logger
from app.settings import get_settings

logger = get_logger()
settings = get_settings()

google_search = get_google_search_tool()
THREAD_MODEL_OVERRIDES: Dict[str, str] = {}

if not settings.openrouter_api_key:
    logger.warning("OPENROUTER_API_KEY не задан — чат работать не будет")


def _bind_tools(llm: ChatOpenAI):
    return llm.bind_tools(
        [
            run_code_in_sandbox,
            browse_website,
            google_search,
            create_chat_attachment_tool,
        ]
    )


def call_ai_query(
    prompt: str | None = None,
    history: list | None = None,
    user_api_key: str | None = None,
    user_model: str | None = None,
    messages: list[dict[str, str]] | None = None,
    thread_id: str | None = None,
    provider_type: str | None = None,
    agent_base_url: str | None = None,
) -> str:
    actual_api_key = user_api_key or settings.openrouter_api_key
    actual_model = user_model or settings.openrouter_model
    provider = (provider_type or "openrouter").strip().lower()

    logger.debug("[AI QUERY] prompt=%s", prompt)
    logger.debug("[AI QUERY] history=%s", history)
    logger.debug("[AI QUERY] incoming_messages=%s", messages)
    logger.debug("[AI QUERY] actual_model=%s", actual_model)
    logger.debug("[AI QUERY] actual_api_key=%s", "***masked***" if actual_api_key else None)
    logger.debug("[AI QUERY] provider_type=%s", provider)
    logger.debug("[AI QUERY] agent_base_url=%s", agent_base_url)

    if thread_id:
        clear_thread_attachments(thread_id)

    if provider == "agentrouter":
        if not actual_api_key:
            raise RuntimeError("Нет доступного OpenAI Compatible API ключа")
        if not agent_base_url:
            raise RuntimeError("Не задан base_url для провайдера OpenAI Compatible")
    else:
        if not actual_api_key:
            raise RuntimeError("Нет доступного OpenRouter API ключа")

    base_url = agent_base_url if provider == "agentrouter" else "https://openrouter.ai/api/v1"
    default_headers = None if provider == "agentrouter" else {
        "HTTP-Referer": "http://localhost",
        "X-Title": "IgorekChatBot",
    }

    llm = ChatOpenAI(
        model=actual_model,
        api_key=actual_api_key,
        base_url=base_url,
        temperature=0.7,
        max_tokens=settings.max_completion_tokens,
        default_headers=default_headers,
    )

    llm_with_tools = _bind_tools(llm)

    conversation: List = []

    if messages:
        for entry in messages:
            role = entry.get("role") if isinstance(entry, dict) else None
            content = entry.get("content") if isinstance(entry, dict) else None
            if content is None or role is None:
                logger.warning("[AI QUERY] Пропущено сообщение без role/content: %s", entry)
                continue

            if role == "system":
                conversation.append(("system", content))
            elif role == "user":
                conversation.append(("human", content))
            elif role == "assistant":
                conversation.append(("ai", content))
            else:
                logger.warning("[AI QUERY] Неизвестная роль сообщения: %s", role)
    else:
        conversation = [("system", "You are a helpful AI assistant.")]
        if history:
            for msg in history:
                role = "human" if msg["type"] == "user" else "ai"
                conversation.append((role, msg["content"]))
        if prompt is not None:
            conversation.append(("human", prompt))

    if not conversation:
        raise RuntimeError("Не удалось сформировать сообщения для модели")

    logger.debug("[AI QUERY] Отправляем messages=%s", conversation)

    try:
        max_tool_steps = 5
        for step in range(1, max_tool_steps + 1):
            ai_msg = llm_with_tools.invoke(conversation)

            logger.debug("[AI QUERY] Ответ модели (step=%s): %s", step, ai_msg)
            logger.debug("[AI QUERY] tool_calls=%s", ai_msg.tool_calls)

            if not ai_msg.tool_calls:
                return ai_msg.content

            conversation.append(ai_msg)

            tool_outputs: List[ToolMessage] = []
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", "unknown")
                logger.info("[TOOL RECURSION] step=%s call=%s", step, tool_name)
                tool_args = tool_call.get("args") if isinstance(tool_call, dict) else getattr(tool_call, "args", {})

                if tool_name == "run_code_in_sandbox":
                    result = run_code_in_sandbox.run(tool_args)
                elif tool_name == "browse_website":
                    result = browse_website.run(tool_args)
                elif tool_name == "google_search":
                    prepared_args = tool_args
                    if isinstance(prepared_args, dict):
                        prepared_args = {
                            **prepared_args,
                            **({"thread_id": thread_id} if thread_id and "thread_id" not in prepared_args else {}),
                        }
                    else:
                        prepared_args = {"query": prepared_args, "thread_id": thread_id}
                    result = google_search.run(prepared_args)
                elif tool_name == "create_chat_attachment":
                    prepared_args = tool_args if isinstance(tool_args, dict) else {"content": tool_args}
                    if thread_id:
                        prepared_args.setdefault("thread_id", thread_id)
                    result = create_chat_attachment_tool.run(prepared_args)
                else:
                    logger.warning("[TOOL RECURSION] step=%s неизвестный инструмент: %s", step, tool_name)
                    result = f"Unsupported tool: {tool_name}"

                tool_outputs.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call.get("id") if isinstance(tool_call, dict) else getattr(tool_call, "id", None),
                    )
                )

            conversation.extend(tool_outputs)
            logger.debug("[AI QUERY] Сообщения после tool_calls шага %s: %s", step, conversation)

        logger.error("[TOOL RECURSION] Превышен лимит последовательных вызовов инструментов")
        if thread_id:
            clear_thread_attachments(thread_id)
        return "Превышен лимит последовательных вызовов инструментов."

    except Exception as exc:  # pragma: no cover
        logger.error("[AI QUERY] Ошибка LangChain API: %s", exc, exc_info=True)
        # Return a fixed marker string that the router can catch, do not include details
        if thread_id:
            clear_thread_attachments(thread_id)
        return "API_ERROR_GENERATING_RESPONSE"
