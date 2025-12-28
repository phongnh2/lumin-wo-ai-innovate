default:
    @just --list

setup:
    mise install
    mise exec -- python -m venv .venv
    .venv/bin/pip install -r requirements.txt

dev:
    .venv/bin/python -m src.main

docker-build:
    docker-compose build

docker-up:
    docker-compose up

docker-down:
    docker-compose down

docker-logs:
    docker-compose logs -f

clean:
    rm -rf .venv __pycache__ src/__pycache__ src/**/__pycache__ data/chroma_db

test-ingest:
    #!/usr/bin/env bash
    set -e
    for f in sample-pdf/*.pdf; do
        echo "Uploading: $f"
        curl -X POST "http://localhost:8765/api/v1/ingest" -F "files=@$f"
        echo ""
    done

test-prompts:
    curl -s "http://localhost:8765/api/v1/prompts" | python -m json.tool

health:
    curl "http://localhost:8765/health"

setup-embedder:
    curl -s -X POST "http://localhost:8765/api/v1/embedder/setup" | python -m json.tool

embedder-status:
    curl -s "http://localhost:8765/api/v1/embedder/status" | python -m json.tool

embedder-task task_uid:
    curl -s "http://localhost:8765/api/v1/embedder/task/{{task_uid}}" | python -m json.tool

search query:
    curl -s -X POST "http://localhost:8765/api/v1/search" \
        -H "Content-Type: application/json" \
        -d '{"query": "{{query}}", "use_hybrid": true, "limit": 5}' | python -m json.tool

search-semantic query:
    curl -s -X POST "http://localhost:8765/api/v1/search/semantic" \
        -H "Content-Type: application/json" \
        -d '{"query": "{{query}}", "limit": 5}' | python -m json.tool
