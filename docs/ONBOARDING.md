# 🎯 FastAPI LangGraph Agent - Onboarding Guide

## 📖 What is This Project?

This is a **production-ready template** for building AI-powered chat applications with enterprise features. Think of it as a sophisticated chatbot framework that can:
- Have conversations with memory (remembers previous messages)
- Use tools (like web search) to answer questions
- Handle multiple users with authentication
- Scale from development to production environments
- Monitor performance and track costs

### Key Use Cases
- Customer support chatbots
- AI assistants for internal tools
- Educational tutoring systems
- Interactive documentation helpers
- Any conversational AI application

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────┐
│                  Frontend                   │
│            (Your React/Vue/etc)             │
└─────────────────┬───────────────────────────┘
                  │ REST API
┌─────────────────▼───────────────────────────┐
│              FastAPI Server                 │
│  ┌─────────────────────────────────────┐   │
│  │   Authentication (JWT)              │   │
│  ├─────────────────────────────────────┤   │
│  │   Rate Limiting                     │   │
│  ├─────────────────────────────────────┤   │
│  │   API Endpoints (/api/v1/*)        │   │
│  └─────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│           LangGraph Agent                   │
│  ┌─────────────────────────────────────┐   │
│  │   Chat State Machine                │   │
│  │   (chat → tool_call → chat)        │   │
│  ├─────────────────────────────────────┤   │
│  │   Tools (Web Search, etc)          │   │
│  ├─────────────────────────────────────┤   │
│  │   Memory (PostgreSQL Checkpoints)   │   │
│  └─────────────────────────────────────┘   │
└────────┬──────────────────┬─────────────────┘
         │                  │
┌────────▼────────┐ ┌───────▼────────┐
│   LLM Provider  │ │   PostgreSQL   │
│  (OpenAI, etc)  │ │   Database     │
└─────────────────┘ └────────────────┘
         │
┌────────▼────────┐
│    Langfuse     │
│  (Observability)│
└─────────────────┘
```

## 📋 Prerequisites & Requirements

### System Requirements
- **Python**: 3.13 or higher
- **PostgreSQL**: 14+ (or Supabase cloud instance)
- **Operating System**: Linux, macOS, or Windows with WSL2
- **RAM**: Minimum 4GB recommended
- **Disk Space**: 1GB for dependencies

### Required Accounts & API Keys
1. **LLM Provider** (Choose one):
   - OpenAI API key (for GPT models) - [Get it here](https://platform.openai.com/api-keys)
   - Google AI API key (for Gemini models) - [Get it here](https://aistudio.google.com/app/apikey) - **FREE**
   - Or any OpenAI-compatible API (Anthropic, Groq, etc.)

2. **Database** (Choose one):
   - Local PostgreSQL installation
   - Supabase account (free tier available) - [Sign up here](https://supabase.com)
   - Any PostgreSQL-compatible database

3. **Optional Services**:
   - Langfuse account for LLM monitoring - [Sign up here](https://langfuse.com)
   - Docker for containerized deployment

## 🚀 Quick Start Guide

### Step 1: Install Dependencies

```bash
# Option 1: Using uv (recommended)
pip install uv
uv sync

# Option 2: Using existing virtual environment
# Activate your virtual environment first
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -e .
pip install langchain-google-genai  # For Gemini support
```

### Step 2: Set Up Environment Configuration

```bash
# Copy the example environment file
cp .env.example .env.development

# Edit the file with your configuration
# You MUST set these values:
```

#### Essential Environment Variables

```bash
# 1. Choose your environment
APP_ENV=development  # Options: development, staging, production

# 2. LLM Configuration (REQUIRED)
LLM_PROVIDER=openai  # Options: "openai" or "gemini"

# For OpenAI:
LLM_API_KEY="sk-..."  # Your OpenAI API key
LLM_MODEL=gpt-4o-mini  # Model to use

# For Gemini (FREE):
LLM_PROVIDER=gemini
LLM_API_KEY="AI..."  # Your Google AI API key (free)
LLM_MODEL=gemini-1.5-flash  # gemini-1.5-flash or gemini-1.5-pro

# 3. Database (REQUIRED)
# For Supabase:
POSTGRES_URL="postgresql://postgres.xxxx:password@aws-0-xxx.pooler.supabase.com:5432/postgres"
# For local PostgreSQL:
POSTGRES_URL="postgresql://username:password@localhost:5432/mydatabase"

# 4. Security (REQUIRED for production)
JWT_SECRET_KEY="your-super-secret-key-change-this"  # Generate with: openssl rand -hex 32

# 5. Monitoring (OPTIONAL but recommended)
LANGFUSE_PUBLIC_KEY="pk-lf-..."  # From Langfuse dashboard
LANGFUSE_SECRET_KEY="sk-lf-..."  # From Langfuse dashboard
```

### Step 3: Database Setup

The application will automatically create tables when it starts, but you need a PostgreSQL database first:

#### Option A: Using Supabase (Easiest)
1. Create a free account at [supabase.com](https://supabase.com)
2. Create a new project
3. Go to Settings → Database
4. Copy the connection string
5. Add it to your `.env.development` file

#### Option B: Local PostgreSQL
```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt-get install postgresql postgresql-contrib

# Create database
sudo -u postgres psql
CREATE DATABASE myapp;
CREATE USER myuser WITH PASSWORD 'mypassword';
GRANT ALL PRIVILEGES ON DATABASE myapp TO myuser;
\q
```

### Step 4: Run the Application

```bash
# Start in development mode (with auto-reload)
make dev

# Or manually:
uv run uvicorn app.main:app --reload --port 8000
```

### Step 5: Verify Installation

1. **Check API Documentation**: http://localhost:8000/docs
2. **Health Check**: http://localhost:8000/health
3. **Root Endpoint**: http://localhost:8000/

## 🧪 Testing the Chat Functionality

### 1. Register a User
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "SecurePassword123!"
  }'
```

### 2. Login (Form Data)
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=SecurePassword123!"

# Save the access_token from the response
```

### 3. Create a Chat Session
```bash
curl -X POST http://localhost:8000/api/v1/auth/session \
  -H "Authorization: Bearer YOUR_LOGIN_ACCESS_TOKEN" \
  -H "Content-Type: application/json"

# This returns a new token with session_id - use this for chat
```

### 4. Send a Chat Message
```bash
curl -X POST http://localhost:8000/api/v1/chatbot/chat \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Hello, what can you help me with?"
      }
    ]
  }'
```

## 📂 Project Structure Explained

```
project/
├── app/                      # Main application code
│   ├── main.py              # FastAPI app entry point
│   ├── api/v1/              # API endpoints
│   │   ├── auth.py          # Login, register, logout
│   │   └── chatbot.py       # Chat endpoints
│   ├── core/                # Core functionality
│   │   ├── config.py        # Environment configuration
│   │   ├── langgraph/       # AI agent logic
│   │   │   ├── graph.py     # Main agent workflow
│   │   │   └── tools/       # Agent tools (search, etc)
│   │   ├── logging.py       # Structured logging
│   │   ├── limiter.py       # Rate limiting
│   │   └── metrics.py       # Prometheus metrics
│   ├── models/              # Database models
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic
│   └── utils/               # Helper functions
├── evals/                   # Model evaluation framework
├── scripts/                 # Deployment scripts
├── prometheus/              # Monitoring config
├── grafana/                 # Dashboard definitions
├── .env.example            # Environment template
├── pyproject.toml          # Python dependencies
├── Makefile                # Common commands
└── docker-compose.yml      # Full stack deployment
```

## 🎯 Common Development Tasks

### Running Different Environments
```bash
make dev        # Development with hot-reload
make staging    # Staging environment
make prod       # Production environment
```

### Code Quality
```bash
make lint       # Check code style
make format     # Auto-format code
```

### Testing
```bash
uv run pytest                    # Run all tests
uv run pytest tests/test_auth.py # Run specific test
uv run pytest --cov=app          # With coverage
```

### Docker Deployment
```bash
# Build and run with Docker
make docker-build-env ENV=development
make docker-run-env ENV=development

# Full stack with monitoring
make docker-compose-up ENV=development
# Access: API (8000), Prometheus (9090), Grafana (3000)
```

## 🔧 Configuration Deep Dive

### Environment-Specific Settings

The app automatically adjusts based on `APP_ENV`:

| Setting | Development | Staging | Production |
|---------|------------|---------|------------|
| Debug | ✅ Enabled | ❌ Disabled | ❌ Disabled |
| Log Level | DEBUG | INFO | WARNING |
| Rate Limits | 1000/day | 500/day | 200/day |
| Error Details | Full | Partial | Minimal |
| Hot Reload | ✅ Yes | ❌ No | ❌ No |

### Key Features by Component

#### 🔐 Authentication System
- JWT tokens with configurable expiration
- Session management in database
- Secure password hashing (bcrypt)
- Protected endpoints with `@require_auth` decorator

#### 🤖 AI Agent (LangGraph)
- **State Machine**: Manages conversation flow
- **Memory**: Persists conversations to PostgreSQL
- **Tools**: Extensible tool system (web search included)
- **Streaming**: Real-time response streaming
- **Fallback**: Automatic fallback to reliable models in production

#### 📊 Monitoring & Observability
- **Langfuse**: Track LLM costs, latency, and quality
- **Prometheus**: System and application metrics
- **Grafana**: Pre-built dashboards for visualization
- **Structured Logging**: JSON logs in production, console in dev

#### 🚦 Rate Limiting
- Per-endpoint limits (customizable)
- User-based and IP-based limiting
- Configurable via environment variables

## 🐛 Troubleshooting Guide

### Common Issues and Solutions

#### 1. "Connection refused" to PostgreSQL
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Check connection string format
# Should be: postgresql://user:password@host:port/database
```

#### 2. "Invalid API Key" from OpenAI
```bash
# Verify your API key
echo $LLM_API_KEY

# Test directly
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer YOUR_KEY"
```

#### 3. "Module not found" errors
```bash
# Ensure you're in the virtual environment
uv sync
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows
```

#### 4. "Session not found" error
```bash
# This error means you need to create a session after login
# Correct flow:
# 1. Login (get login token)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your@email.com&password=yourpassword"

# 2. Create session (get session token)
curl -X POST http://localhost:8000/api/v1/auth/session \
  -H "Authorization: Bearer LOGIN_TOKEN"

# 3. Use session token for chat
curl -X POST http://localhost:8000/api/v1/chatbot/chat \
  -H "Authorization: Bearer SESSION_TOKEN" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

#### 5. Login returns "Field required" error
```bash
# Login uses form data, not JSON
# ❌ Wrong (JSON):
curl -H "Content-Type: application/json" -d '{"username":"test"}'

# ✅ Correct (Form data):
curl -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=password"
```

#### 6. Port already in use
```bash
# Find process using port 8000
lsof -i :8000  # Linux/Mac
netstat -ano | findstr :8000  # Windows

# Kill the process or use different port
uvicorn app.main:app --port 8001
```

## 📚 Next Steps

### For Development
1. Explore the Swagger UI at http://localhost:8000/docs
2. Add custom tools in `app/core/langgraph/tools/`
3. Customize the system prompt in `app/core/prompts/`
4. Add new API endpoints in `app/api/v1/`

### For Production
1. Set up proper SSL/TLS certificates
2. Configure a reverse proxy (nginx/caddy)
3. Set up backup strategies for PostgreSQL
4. Configure monitoring alerts in Grafana
5. Implement CI/CD pipelines

### Learning Resources
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Documentation](https://python.langchain.com/)
- [Langfuse Documentation](https://langfuse.com/docs)

## 💡 Tips for Success

1. **Start Simple**: Get the basic chat working before adding features
2. **Monitor Costs**: Use Langfuse to track LLM usage and costs
3. **Test Locally**: Use development environment before deploying
4. **Check Logs**: Structured logging helps debug issues quickly
5. **Use Rate Limits**: Protect your API from abuse
6. **Version Control**: Commit your `.env.example` but never `.env`

## 🆘 Getting Help

- **API Issues**: Check http://localhost:8000/docs for endpoint details
- **Database Issues**: Verify connection string and credentials
- **LLM Issues**: Check API key and model availability
- **Performance**: Monitor with Grafana dashboards
- **Errors**: Check logs in `logs/` directory or console output

---

**Ready to build?** Start with `make dev` and explore the API at http://localhost:8000/docs! 🚀