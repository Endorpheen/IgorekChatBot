# TEST_INDEX

## Backend

| Type | Path | Purpose |
| --- | --- | --- |
| unit | tests/unit/test_image_generation_fingerprint.py | Validates PBKDF2 fingerprint derivation for BYOK image providers (64-char hex, deterministic, differentiates keys). |
| integration | tests/integration/test_chat_attachments.py | Covers chat-generated attachments: creation, validation, and signed download flow via FastAPI router. |
| integration | tests/integration/test_document_analysis.py | Exercises document analysis pipeline including sandbox interaction stubs and sanitized responses. |
| integration | tests/integration/test_image_generation_redirects.py | Ensures image generation redirect endpoints stay relative, obey session checks, and integrate with signed links. |
| integration | tests/integration/test_google_search_provider.py | Validates caching, rate limiting, and graceful error handling of Google Custom Search integration. |
| integration | tests/integration/test_image_analysis.py | Verifies image-understanding pipeline switches between OpenRouter and OpenAI Compatible providers safely. |
| integration | tests/integration/test_mcp_tools.py | Exercises Obsidian client wiring plus sandbox/browser StructuredTool fallbacks and error paths. |
| integration | tests/integration/test_upload_cleaner.py | Verifies TTL pruning, size-based cleanup, async task lifecycle, and resilient handling of filesystem edge cases. |

## Frontend

| Type | Path | Purpose |
| --- | --- | --- |
| unit | web-ui/tests/unit/session.test.ts | Verifies image session id helper prefers `crypto.randomUUID`, falls back to `crypto.getRandomValues`, and persists deterministic ids. |
| unit | web-ui/tests/unit/imageAnalysisProvider.test.ts | Ensures image analysis API payloads depend on the active provider and validates configuration hints. |
| unit | web-ui/tests/unit/agentRouterFallback.test.ts | Tests SettingsPanel provider switching and manual model input fallback logic on API errors (400/404). |
| e2e | web-ui/tests/e2e/basic.e2e.spec.ts | Playwright smoke navigation tests for chat sorting and image generation panel basic functionality. |
| e2e | web-ui/tests/e2e/chatFlow.e2e.spec.ts | Full chat scenarios with API mocking, message sending, and IndexedDB history recovery. |
| e2e | web-ui/tests/e2e/imageGeneration.e2e.spec.ts | Comprehensive image generation E2E tests with API mocking, validation, error handling, and staging integration. |
