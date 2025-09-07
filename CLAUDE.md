# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the Application
```bash
# Local development with hot reload
make dev

# Production mode
make prod

# Staging mode  
make staging
```

### Code Quality
```bash
# Linting with ruff
make lint
ruff check .

# Formatting with ruff
make format
ruff format .
```

### Testing
```bash
# Run tests with pytest
uv run pytest

# Run specific test file
uv run pytest tests/test_file.py

# Run tests with coverage
uv run pytest --cov=app
```

### Docker Operations
```bash
# Build and run for specific environment
make docker-build-env ENV=development
make docker-run-env ENV=development

# Full stack with monitoring
make docker-compose-up ENV=development
```

### Model Evaluation
```bash
# Interactive evaluation
make eval ENV=development

# Quick evaluation with defaults
make eval-quick ENV=development
```

### Chatwoot Integration
```bash
# Test Chatwoot integration health
curl http://localhost:8000/api/v1/chatwoot/health

# View Chatwoot configuration
curl http://localhost:8000/api/v1/chatwoot/config

# Webhook endpoint for Chatwoot
# POST http://localhost:8000/api/v1/chatwoot/webhook
```

## Architecture Overview

### Core Components

1. **FastAPI Application** (`app/main.py`)
   - Entry point for the application
   - Configures middleware, rate limiting, CORS, and metrics
   - Environment-aware configuration via `app/core/config.py`

2. **LangGraph Agent** (`app/core/langgraph/graph.py`)
   - Manages AI agent workflow with tool calling capabilities
   - Implements chat/tool_call state machine pattern
   - Integrates with Langfuse for observability
   - PostgreSQL-based conversation persistence via AsyncPostgresSaver

3. **Authentication System** (`app/api/v1/auth.py`, `app/utils/auth.py`)
   - JWT-based authentication with configurable expiration
   - Session management in PostgreSQL
   - Password hashing with bcrypt

4. **Environment Management** (`app/core/config.py`)
   - Supports development, staging, production, test environments
   - Dynamic configuration loading from `.env.[environment]` files
   - Environment-specific defaults and overrides

5. **Rate Limiting** (`app/core/limiter.py`)
   - SlowAPI-based rate limiting
   - Configurable per-endpoint limits
   - Environment-aware defaults

6. **Monitoring & Observability**
   - Prometheus metrics collection (`app/core/metrics.py`)
   - Grafana dashboards for visualization
   - Langfuse integration for LLM tracing
   - Structured logging with environment-specific formatting

7. **Chatwoot Integration** (`app/api/v1/chatwoot.py`, `app/services/chatwoot.py`)
   - Webhook authentication with HMAC signature validation
   - Bidirectional message flow between Chatwoot and LangGraph agent
   - Session management using Chatwoot conversation/contact IDs
   - Comprehensive error handling and retry logic
   - Prometheus metrics for webhook processing and API calls

### Key Design Patterns

- **Async/Await Throughout**: All database operations and LLM calls are async
- **Environment-First Configuration**: All settings adapt based on APP_ENV
- **Graceful Degradation**: Production mode continues with reduced functionality if services fail
- **Checkpoint Pattern**: Conversation state persisted to PostgreSQL for reliability

### Database Schema

The application uses SQLModel ORM with these core tables:
- `users`: User accounts with authentication
- `sessions`: Active user sessions
- `threads`: Conversation threads
- `checkpoint_*`: LangGraph state persistence tables

### Tool Integration

Tools are defined in `app/core/langgraph/tools/` and automatically bound to the LLM:
- DuckDuckGo search tool for web queries
- Extensible architecture for adding new tools

### API Structure

All API endpoints follow `/api/v1/` prefix:
- `/auth/*`: Authentication endpoints (register, login, logout)
- `/chatbot/*`: Chat interaction endpoints (chat, stream, messages, history)
- `/chatwoot/*`: Chatwoot webhook and integration endpoints

### Environment Variables

Critical environment variables that must be set:
- `APP_ENV`: Environment (development/staging/production)
- `LLM_API_KEY`: OpenAI or compatible LLM API key
- `POSTGRES_URL`: PostgreSQL connection string
- `JWT_SECRET_KEY`: Secret for JWT signing
- `LANGFUSE_PUBLIC_KEY` & `LANGFUSE_SECRET_KEY`: For LLM observability

Chatwoot integration variables (optional):
- `CHATWOOT_ENABLED`: Enable/disable Chatwoot integration
- `CHATWOOT_BASE_URL`: Chatwoot instance URL
- `CHATWOOT_API_ACCESS_TOKEN`: API token for Chatwoot
- `CHATWOOT_ACCOUNT_ID`: Chatwoot account ID
- `CHATWOOT_TIMEOUT`: Request timeout in seconds (default: 30)
- `CHATWOOT_MAX_RETRIES`: Maximum API retry attempts (default: 3)

See `.env.example` for complete list and defaults.