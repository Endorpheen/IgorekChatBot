# Tasks.md — описание доступных команд MCP CLI

tasks:

  - name: list
    description: "Показать список доступных инструментов MCP сервера."
    command: |
      uv run python mcp-cli.py list

  - name: list-notes
    description: "Вывести список всех .md файлов в хранилище."
    command: |
      uv run python mcp-cli.py list-notes

  - name: search
    description: "Искать заметки по ключевому слову."
    usage: "uv run python mcp-cli.py search <ключевое_слово>"
    examples:
      - "uv run python mcp-cli.py search docker"
      - "uv run python mcp-cli.py search nginx"

  - name: fetch
    description: "Получить содержимое заметки по ID."
    usage: "uv run python mcp-cli.py fetch \"<ID>\""
    examples:
      - "uv run python mcp-cli.py fetch \"Servers Setup/Matrix Synapse Server.md\""

  - name: fetch-save
    description: "Получить заметку и сохранить её в файл."
    usage: "uv run python mcp-cli.py fetch \"<ID>\" --save <файл>"
    examples:
      - "uv run python mcp-cli.py fetch \"Servers Setup/Matrix Synapse Server.md\" --save out.md"

  - name: ask-llm
    description: "Задать вопрос локальной LLM (qwen/qwen3-4b-2507)."
    usage: "uv run python mcp-cli.py ask-llm \"<вопрос>\" [--context \"<ID заметки>\"]"
    examples:
      - "uv run python mcp-cli.py ask-llm \"Объясни концепцию Docker\""
      - "uv run python mcp-cli.py ask-llm \"Что в этой заметке?\" --context \"My Notes/Important.md\""

  - name: ai-query
    description: "AI запрос с доступом к инструментам vault (поиск и получение заметок)."
    usage: "uv run python mcp-cli.py ai-query \"<запрос>\""
    examples:
      - "uv run python mcp-cli.py ai-query \"Найди заметки о Docker и объясни основы\""
      - "uv run python mcp-cli.py ai-query \"Что я записал о настройке сервера?\""
