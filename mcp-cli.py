#!/usr/bin/env python3
import requests
import sys
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
import argparse

# Конфигурация
MCP_URL = "MCP_URL_REMOVED"
console = Console()

def rpc_call(method, params=None, _id=1):
    payload = {"jsonrpc": "2.0", "id": _id, "method": method}
    if params:
        payload["params"] = params
    r = requests.post(MCP_URL, json=payload, headers={"Content-Type": "application/json"})
    r.raise_for_status()
    return r.json()

def list_tools():
    resp = rpc_call("tools/list")
    tools = resp["result"]["tools"]
    table = Table(title="MCP Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")
    for t in tools:
        table.add_row(t["name"], t["description"])
    console.print(table)

def list_notes():
    resp = rpc_call("tools/call", {
        "name": "search",
        "arguments": {"query": ""}
    })
    results = resp["result"]["content"][0]["json"]["results"]
    if not results:
        console.print("[red]Нет заметок[/red]")
        return
    table = Table(title="Все заметки в vault")
    table.add_column("ID", style="yellow")
    for r in results:
        table.add_row(r["id"])
    console.print(table)

def search(query, since=None):
    args = {"query": query}
    if since:
        args["since"] = since
    resp = rpc_call("tools/call", {
        "name": "search",
        "arguments": args
    })
    results = resp["result"]["content"][0]["json"]["results"]
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
        snippet = Text(r["snippet"].replace("\n", " ")[:120] + "...")
        if query:
            snippet.highlight_words([query], style="bold yellow")
        modified = r.get("modified", "-")
        table.add_row(r["id"], snippet, modified)
    console.print(table)

def fetch(note_id, save_path=None):
    resp = rpc_call("tools/call", {
        "name": "fetch",
        "arguments": {"id": note_id}
    })
    content = resp.get("result", {}).get("content", [])[0]["json"].get("content")
    if not content:
        console.print("[red]Файл не найден[/red]")
        return
    if save_path:
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"[green]Заметка сохранена в {save_path}[/green]")
    else:
        syntax = Syntax(content, "markdown", theme="monokai", line_numbers=True)
        console.print(syntax)

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

    args = parser.parse_args()

    if args.command == "list":
        list_tools()
    elif args.command == "list-notes":
        list_notes()
    elif args.command == "search":
        search(args.query, args.since)
    elif args.command == "fetch":
        fetch(args.id, args.save)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
