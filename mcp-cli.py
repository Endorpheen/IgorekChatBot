#!/usr/bin/env python3
import requests
import sys
import json
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
import argparse
import os
from dotenv import load_dotenv
load_dotenv()




# Конфигурация
console = Console()
MCP_URL = os.getenv("MCP_URL")
if not MCP_URL:
    console.print("[red]Переменная окружения MCP_URL не установлена.[/red]")
    console.print("Добавьте MCP_URL в .env или экспортируйте её в окружение")
    sys.exit(1)

def rpc_call(method, params=None, _id=1):
    token = os.getenv("AUTH_TOKEN")
    if not token:
        console.print("[red]Переменная окружения AUTH_TOKEN не установлена.[/red]")
        console.print("Установите токен, например: export AUTH_TOKEN=ВАШ_ТОКЕН")
        sys.exit(1)

    payload = {"jsonrpc": "2.0", "id": _id, "method": method}
    if params:
        payload["params"] = params

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        r = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Сетевая ошибка: {e}[/red]")
        sys.exit(1)
    except ValueError:
        console.print("[red]Ошибка парсинга JSON ответа[/red]")
        sys.exit(1)

    if "error" in data:
        console.print(f"[red]RPC error: {data['error']}[/red]")
        sys.exit(1)
    if "result" not in data:
        console.print("[red]Некорректный ответ сервера[/red]")
        sys.exit(1)
    return data

def list_tools():
    resp = rpc_call("tools/list")
    tools = (resp.get("result", {}) or {}).get("tools") or []
    if not tools:
        console.print("[red]Инструменты не найдены[/red]")
        return
    table = Table(title="MCP Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")
    for t in tools:
        name = (t or {}).get("name") or "-"
        desc = (t or {}).get("description") or "-"
        table.add_row(name, desc)
    console.print(table)

def list_notes():
    resp = rpc_call("tools/call", {
        "name": "search",
        "arguments": {"query": ""}
    })
    result = resp.get("result", {})
    content_items = result.get("content") or []
    results = []
    if content_items and isinstance(content_items, list):
        first = content_items[0]
        if isinstance(first, dict):
            json_obj = first.get("json") or {}
            results = json_obj.get("results") or []

    if not results:
        console.print("[red]Нет заметок[/red]")
        return
    table = Table(title="Все заметки в vault")
    table.add_column("ID", style="yellow")
    for r in results:
        note_id = r.get("id") or "-"
        table.add_row(note_id)
    console.print(table)

def search(query, since=None):
    args = {"query": query}
    if since:
        args["since"] = since
    resp = rpc_call("tools/call", {
        "name": "search",
        "arguments": args
    })
    result = resp.get("result", {})
    content_items = result.get("content") or []
    results = []
    if content_items and isinstance(content_items, list):
        first = content_items[0]
        if isinstance(first, dict):
            json_obj = first.get("json") or {}
            results = json_obj.get("results") or []

    if not results:
        console.print("[red]Ничего не найдено[/red]")
        return
    title = f"Search results for '{query}'"
    if since:
        title += f" (since {since})"
    table = Table(title=title)
    table.add_column("ID", style="yellow")
    table.add_column("Snippet", style="white")
    table.add_column("Modified", style="cyan")
    for r in results:
        snippet_text = (r.get("snippet") or "").replace("\n", " ")
        snippet_text = (snippet_text[:120] + "...") if len(snippet_text) > 120 else snippet_text
        snippet = Text(snippet_text)
        if query:
            snippet.highlight_words([query], style="bold yellow")
        modified = r.get("modified") or "-"
        table.add_row(str(r.get("id") or "-"), snippet, modified)
    console.print(table)

def fetch(note_id, save_path=None):
    resp = rpc_call("tools/call", {
        "name": "fetch",
        "arguments": {"id": note_id}
    })
    result = resp.get("result", {})
    content_items = result.get("content") or []
    content = None
    if content_items and isinstance(content_items, list):
        first = content_items[0]
        if isinstance(first, dict):
            json_obj = first.get("json") or {}
            content = json_obj.get("content")
    if not content:
        console.print("[red]Файл не найден[/red]")
        return
    if save_path:
        dir_name = os.path.dirname(save_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"[green]Заметка сохранена в {save_path}[/green]")
    else:
        syntax = Syntax(content, "markdown", theme="monokai", line_numbers=True)
        console.print(syntax)

def ask_llm(prompt, context=None):
    llm_url = "http://192.168.0.155:8010/v1/chat/completions"
    messages = []
    if context:
        # Если контекст указан, получаем содержимое заметки
        try:
            resp = rpc_call("tools/call", {
                "name": "fetch",
                "arguments": {"id": context}
            })
            result = resp.get("result", {})
            content_items = result.get("content") or []
            ctx_content = None
            if content_items and isinstance(content_items, list):
                first = content_items[0]
                if isinstance(first, dict):
                    json_obj = first.get("json") or {}
                    ctx_content = json_obj.get("content")
            if ctx_content:
                messages.append({"role": "system", "content": f"Контекст из заметки:\n{ctx_content}"})
            else:
                console.print("[yellow]Контекст не найден, игнорируем[/yellow]")
        except:
            console.print("[yellow]Ошибка получения контекста, игнорируем[/yellow]")
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": "qwen/qwen3-4b-2507",
        "messages": messages,
        "max_tokens": 1000
    }

    try:
        r = requests.post(llm_url, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        console.print(Syntax(response_text, "markdown", theme="monokai"))
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Ошибка подключения к LLM: {e}[/red]")
    except ValueError:
        console.print("[red]Ошибка парсинга ответа LLM[/red]")

def execute_tool(tool_name, arguments):
    if tool_name == "search":
        query = arguments.get("query", "")
        since = arguments.get("since")
        # Выполнить поиск
        resp = rpc_call("tools/call", {
            "name": "search",
            "arguments": {"query": query, "since": since} if since else {"query": query}
        })
        result = resp.get("result", {})
        content_items = result.get("content") or []
        results = []
        if content_items and isinstance(content_items, list):
            first = content_items[0]
            if isinstance(first, dict):
                json_obj = first.get("json") or {}
                results = json_obj.get("results") or []
        return [{"id": r.get("id"), "snippet": r.get("snippet"), "modified": r.get("modified")} for r in results]
    elif tool_name == "fetch":
        note_id = arguments.get("id")
        resp = rpc_call("tools/call", {
            "name": "fetch",
            "arguments": {"id": note_id}
        })
        result = resp.get("result", {})
        content_items = result.get("content") or []
        content = None
        if content_items and isinstance(content_items, list):
            first = content_items[0]
            if isinstance(first, dict):
                json_obj = first.get("json") or {}
                content = json_obj.get("content")
        return content
    return "Tool not found"

def ai_query(prompt):
    llm_url = "http://192.168.0.155:8010/v1/chat/completions"
    messages = [
        {"role": "system", "content": "You are an AI assistant with access to tools for searching and fetching notes from a vault. Use the tools when needed to answer questions about the user's notes."},
        {"role": "user", "content": prompt}
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search notes in vault",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "since": {"type": "string", "description": "Filter by time, e.g., 7d, 12h"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "fetch",
                "description": "Fetch note by id",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Note ID"}
                    },
                    "required": ["id"]
                }
            }
        }
    ]

    while True:
        payload = {
            "model": "qwen/qwen3-4b-2507",
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto"
        }

        try:
            r = requests.post(llm_url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            message = data.get("choices", [{}])[0].get("message", {})
            content = message.get("content")
            tool_calls = message.get("tool_calls")

            if content:
                console.print(Syntax(content, "markdown", theme="monokai"))

            if not tool_calls:
                break

            messages.append(message)

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])
                result = execute_tool(tool_name, arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result)
                })

        except requests.exceptions.RequestException as e:
            console.print(f"[red]Ошибка подключения к LLM: {e}[/red]")
            break
        except ValueError:
            console.print("[red]Ошибка парсинга ответа LLM[/red]")
            break

def main():
    parser = argparse.ArgumentParser(description="MCP Vault CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list")
    subparsers.add_parser("list-notes")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query", nargs="?", default="")
    search_parser.add_argument("--since", help="Фильтр по времени: 7d, 12h, 30m")

    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("id")
    fetch_parser.add_argument("--save", help="Сохранить заметку в файл")

    ask_parser = subparsers.add_parser("ask-llm")
    ask_parser.add_argument("prompt", help="Вопрос для LLM")
    ask_parser.add_argument("--context", help="ID заметки для контекста")

    ai_parser = subparsers.add_parser("ai-query")
    ai_parser.add_argument("query", help="Запрос к AI с доступом к инструментам vault")

    args = parser.parse_args()

    if args.command == "list":
        list_tools()
    elif args.command == "list-notes":
        list_notes()
    elif args.command == "search":
        search(args.query, args.since)
    elif args.command == "fetch":
        fetch(args.id, args.save)
    elif args.command == "ask-llm":
        ask_llm(args.prompt, args.context)
    elif args.command == "ai-query":
        ai_query(args.query)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
