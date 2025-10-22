# Предварительная фиксация состояния (2025-10-21)

- Версия backend: `0.1.0` (`pyproject.toml`)
- Активные роутеры FastAPI (включая внутренние):
  - `/chat` (POST, include_in_schema=False)
  - `/image/analyze` (POST, include_in_schema=False)
  - `/file/analyze` (POST, include_in_schema=False)
  - `/image/generate` (POST, include_in_schema=False)
  - `/image/jobs/{job_id}` (GET, include_in_schema=False)
  - `/image/jobs/{job_id}/result` (GET, include_in_schema=False)
  - `/image/validate` (POST, include_in_schema=False)
  - `/image/files/{job_id}.webp` (GET, include_in_schema=False)
  - `/image/providers`, `/image/providers/search` (GET, include_in_schema=False)
  - `/signed/image/jobs/status`, `/signed/image/jobs/result` (GET, include_in_schema=False)
  - `/uploads/{filename}` (GET, include_in_schema=False)
  - `/signed/uploads` (GET, include_in_schema=False)
  - `/api/mcp/search`, `/api/mcp/fetch` (POST, include_in_schema=False)
  - `/api/providers/agentrouter/models` (GET, include_in_schema=False)
  - Публичные GET: `/`, `/images`, `/images/`, `/robots.txt`, `/sitemap.xml`, `/google{path}`

- Публичная схема OpenAPI (доступна только после Basic Auth): включает только безопасные GET (`/`, `/images`, `/images/`, `/robots.txt`, `/sitemap.xml`, `/google{path}`).
- CORS: `allow_origins = ["https://igorekchatbot.ru", "https://igorek.end0databox.duckdns.org"]`, `allow_origin_regex = "^https://(igorekchatbot\\.ru|igorek\\.end0databox\\.duckdns\\.org)$"`.
