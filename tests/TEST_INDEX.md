# TEST_INDEX

## Backend

| Type | Path | Purpose |
| --- | --- | --- |
| unit | tests/unit/test_image_generation_fingerprint.py | Validates PBKDF2 fingerprint derivation for BYOK image providers (64-char hex, deterministic, differentiates keys). |
| integration | tests/integration/test_chat_attachments.py | Covers chat-generated attachments: creation, validation, and signed download flow via FastAPI router. |
| integration | tests/integration/test_document_analysis.py | Exercises document analysis pipeline including sandbox interaction stubs and sanitized responses. |
| integration | tests/integration/test_image_generation_redirects.py | Ensures image generation redirect endpoints stay relative, obey session checks, and integrate with signed links. |

## Frontend

| Type | Path | Purpose |
| --- | --- | --- |
| unit | web-ui/tests/unit/session.test.ts | Verifies image session id helper prefers `crypto.randomUUID`, falls back to `crypto.getRandomValues`, and persists deterministic ids. |
| e2e | *(empty)* | Reserve `web-ui/tests/e2e/*.e2e.spec.ts` for Playwright scenarios (none implemented yet). |
