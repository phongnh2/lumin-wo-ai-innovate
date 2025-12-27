# PDF Prompt Agent

An AI-powered system that analyzes PDF documents, generates intelligent prompt templates, and provides AI-powered search via Meilisearch.

## Features

- **PDF to Vector Database**: Upload PDF files and convert them into a searchable context vector database
- **Smart Prompt Generation**: AI generates contextual prompt templates optimized for semantic search
- **AI-Powered Search**: Hybrid search combining full-text and semantic search via Meilisearch
- **Local & Free**: Uses HuggingFace models locally (no API keys required)

## Quick Start

### Using Docker (Recommended)

```bash
docker-compose up --build
```

### Manual Setup

```bash
just setup
just dev
```

The API will be available at `http://localhost:8765`

## API Endpoints

### 1. Upload PDFs and Create Vector Database

**POST** `/api/v1/ingest`

```bash
curl -X POST "http://localhost:8765/api/v1/ingest" \
  -F "files=@document1.pdf" \
  -F "files=@document2.pdf"
```

### 2. Generate Prompt Templates

**GET** `/api/v1/prompts`

Generate AI-powered prompt templates based on the ingested PDF context.

```bash
curl "http://localhost:8765/api/v1/prompts"
```

Response:
```json
{
  "prompt": [
    "I need a form to handle policy for ___",
    "Find a template for seating related to ___",
    "Show me document forms for ___"
  ],
  "placeholders": ["topic", "industry", "region"],
  "context_summary": "..."
}
```

### 3. Generate Follow-up Queries

**POST** `/api/v1/prompts/follow-up`

Generate contextual follow-up queries based on a user prompt.

```bash
curl -X POST "http://localhost:8765/api/v1/prompts/follow-up" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Find compliance templates for IT industries in the US"}'
```

Response:
```json
{
  "original_prompt": "Find compliance templates for IT industries in the US",
  "follow_up_queries": [
    "Add examples from enterprise software companies.",
    "Include third-party audit checklists.",
    "Show only documents updated this year."
  ]
}
```

### 4. Setup Meilisearch Embedder (One-time)

**POST** `/api/v1/embedder/setup`

Configure HuggingFace embedder for AI-powered search.

```bash
curl -X POST "http://localhost:8765/api/v1/embedder/setup"
```

### 5. Check Embedder Status

**GET** `/api/v1/embedder/status`

```bash
curl "http://localhost:8765/api/v1/embedder/status"
```

### 6. AI-Powered Search (Hybrid)

**POST** `/api/v1/search`

Search with hybrid mode (full-text + semantic).

```bash
curl -X POST "http://localhost:8765/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "I need a form for employee onboarding", "use_hybrid": true, "limit": 10}'
```

Response:
```json
{
  "query": "I need a form for employee onboarding",
  "hits": [
    {"id": 1, "title": "Employee Onboarding Checklist", "description": "..."},
    {"id": 2, "title": "New Hire Form", "description": "..."}
  ],
  "total_hits": 25,
  "processing_time_ms": 12,
  "hybrid_enabled": true
}
```

### 7. Semantic-Only Search

**POST** `/api/v1/search/semantic`

Pure semantic search (100% meaning-based).

```bash
curl -X POST "http://localhost:8765/api/v1/search/semantic" \
  -H "Content-Type: application/json" \
  -d '{"query": "documents for school anti-bullying", "limit": 10}'
```

### 8. Health Check

**GET** `/health`

```bash
curl "http://localhost:8765/health"
```

## Just Commands

```bash
just setup           # Setup Python environment
just dev             # Run development server
just test-ingest     # Upload all PDFs from sample-pdf/
just test-prompts    # Generate prompt templates
just setup-embedder  # Configure Meilisearch embedder
just embedder-status # Check embedder configuration
just search "query"  # Hybrid search
just search-semantic "query"  # Semantic search only
```

## Project Structure

```
├── docker-compose.yml
├── Dockerfile
├── justfile
├── mise.toml
├── requirements.txt
├── src/
│   ├── main.py
│   ├── api/
│   │   └── routes.py
│   ├── services/
│   │   ├── pdf_processor.py
│   │   ├── vector_store.py
│   │   ├── prompt_generator.py
│   │   ├── followup_generator.py
│   │   └── meilisearch_client.py
│   ├── models/
│   │   └── schemas.py
│   └── config/
│       ├── settings.py
│       ├── prompt_templates.json
│       └── followup_config.json
├── data/
│   └── chroma_db/
└── sample-pdf/
```

## Tech Stack

- **FastAPI**: Modern Python web framework
- **Meilisearch**: AI-powered search engine (local, port 7700)
- **ChromaDB**: Local vector database for PDF context
- **Sentence Transformers**: `all-MiniLM-L6-v2` for embeddings
- **Transformers**: `google/flan-t5-small` for prompt generation
- **PyPDF2**: PDF text extraction

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | API host |
| `PORT` | `8765` | API port |
| `CHROMA_PATH` | `./data/chroma_db` | Vector DB storage path |
| `MEILISEARCH_HOST` | `http://localhost:7700` | Meilisearch URL |
| `MEILISEARCH_API_KEY` | `` | Meilisearch API key (optional) |
| `MEILISEARCH_INDEX` | `form` | Meilisearch index name |

## License

MIT
