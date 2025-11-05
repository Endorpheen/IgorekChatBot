# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Igorek ChatBot is a configurable multimodal LLM interface built with FastAPI (backend) and React/Vite (frontend). It's a BYOK (Bring Your Own Keys) system where users provide their own API keys for various providers. The application supports text, images, and tool calling with features like Google Search integration, image generation, and analysis capabilities.
Всегда общайся с пользователем на РУССКОМ ЯЗЫКЕ!!!!!!
## Architecture

### Backend (FastAPI)
- **Entry point**: `app/main.py` - Main FastAPI application
- **Core features**:
  - `app/features/chat/` - Chat functionality with router and service layers
  - `app/features/image_generation/` - Multi-provider image generation (Together AI, Replicate, Stability AI)
  - `app/features/image_analysis/` - Image analysis service
  - `app/features/search/` - Google Search integration with official API
  - `app/features/mcp/` - MCP (Model Context Protocol) client integration
  - `app/features/uploads/` - File upload handling with cleanup
  - `app/features/document_analysis/` - Document analysis capabilities
- **Security layer**: `app/security_layer/` - Session management, rate limiting, signed links for downloads
- **Middlewares**: `app/middlewares/` - CORS, security, and session handling
- **Provider adapters**: `app/features/providers/` - OpenAI-compatible provider implementations

### Frontend (React/Vite)
- **Entry point**: `web-ui/src/main.tsx`
- **Core components**:
  - `ChatPanel.tsx` - Main chat interface with thread management
  - `ImageGenerationPanel.tsx` - Image generation UI with provider selection
  - `SettingsPanel.tsx` - BYOK key management and provider configuration
  - `McpPanel.tsx` - MCP tool integration interface
- **Storage**: IndexedDB-based storage in `src/storage/` for messages, settings, and provider preferences
- **Utilities**: API utilities, image provider helpers, session management

### Key Patterns
- **Feature-based organization**: Both backend and frontend are organized by feature modules
- **Service layer pattern**: Business logic separated from HTTP handlers
- **BYOK architecture**: All API keys are client-side managed with optional encryption
- **Multimodal support**: Text, images, and tool calling integrated throughout the stack

## Common Development Commands

### Backend
- **Run tests**: `uv run --with pytest-cov pytest --cov=app --cov-report=xml:reports/backend/coverage.xml --cov-report=term`
- **Development server**: `uv run uvicorn app.main:app --reload`

### Frontend
- **Development**: `npm --prefix web-ui run dev`
- **Build**: `npm --prefix web-ui run build`
- **Lint**: `npm --prefix web-ui run lint`
- **Unit tests**: `npm --prefix web-ui run test:unit`
- **E2E tests**: `npm --prefix web-ui run test:e2e`
- **DOM tests**: `npm --prefix web-ui run test:dom`

### Full Stack
- **Run all tests**: `npm run test:all` (from root)
- **Lint frontend**: `npm run lint` (from root)

## Development Notes

### Backend Development
- The application uses dependency injection patterns defined in `app/security_layer/dependencies.py`
- All routes require proper session handling via the security layer
- File uploads use signed URLs and automatic cleanup via `app/features/uploads/cleaner.py`
- Provider implementations follow the OpenAI-compatible interface pattern

### Frontend Development
- State management uses React hooks with IndexedDB persistence
- Component structure is feature-based with shared utilities
- All API calls go through centralized utilities in `src/utils/api.ts`
- Image handling supports both upload and generation with provider-specific configurations

### Testing
- Backend uses pytest with coverage reporting
- Frontend uses Vitest for unit tests and Playwright for E2E tests
- Test utilities are centralized for both backend and frontend testing
- Coverage reports are generated in XML format for CI integration

### Security Considerations
- All secrets are masked in logs
- BYOK keys can be encrypted client-side with optional PIN
- No chat history is stored on the server
- Downloads use time-limited signed URLs
- Rate limiting is implemented at the security layer
