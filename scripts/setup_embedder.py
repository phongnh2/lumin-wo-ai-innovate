"""
Configure the HuggingFace vector embedder in Meilisearch.

- Enables the experimental vectorStore feature (required for Meilisearch v1.6)
- Registers 'form-embedder' using sentence-transformers/all-MiniLM-L6-v2
- Polls until the task succeeds or fails

Run:
  python scripts/setup_embedder.py
"""

import os
import sys
import time

import meilisearch
import requests as http_requests

MEILISEARCH_HOST = os.getenv("MEILISEARCH_HOST", "http://localhost:7700")
MEILISEARCH_API_KEY = os.getenv("MEILISEARCH_API_KEY", "")
MEILISEARCH_INDEX = os.getenv("MEILISEARCH_INDEX", "form")

EMBEDDER_NAME = "form-embedder"
EMBEDDER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TASK_TIMEOUT_S = 300


def wait_for_task(client: meilisearch.Client, task_uid: int, timeout: int = TASK_TIMEOUT_S) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get_task(task_uid)
        if task.status in ("succeeded", "failed", "canceled"):
            return task.status
        time.sleep(2)
    raise TimeoutError(f"Task {task_uid} did not complete within {timeout}s")


def enable_vector_store() -> None:
    """Enable the experimental vectorStore feature via direct HTTP (SDK v0.31 lacks this method)."""
    print("Enabling experimental vectorStore feature...")
    url = f"{MEILISEARCH_HOST}/experimental-features"
    headers = {"Content-Type": "application/json"}
    if MEILISEARCH_API_KEY:
        headers["Authorization"] = f"Bearer {MEILISEARCH_API_KEY}"

    resp = http_requests.patch(url, json={"vectorStore": True}, headers=headers)
    if resp.status_code in (200, 202):
        print(f"vectorStore feature enabled: {resp.json()}")
    else:
        print(f"WARNING: Failed to enable vectorStore ({resp.status_code}): {resp.text}")
        print("Continuing — feature may already be enabled.")


def setup_embedder(client: meilisearch.Client) -> None:
    index = client.index(MEILISEARCH_INDEX)

    embedder_config = {
        EMBEDDER_NAME: {
            "source": "huggingFace",
            "model": EMBEDDER_MODEL,
            "documentTemplate": (
                "A form template titled '{{doc.title}}'. "
                "{{doc.description}} {{doc.subTitle}}"
            ),
        }
    }

    print(f"Submitting embedder config: {EMBEDDER_NAME} ({EMBEDDER_MODEL}) ...")
    task = index.update_embedders(embedder_config)
    print(f"Task submitted: uid={task.task_uid}. Waiting for completion (this may take a while) ...")

    status = wait_for_task(client, task.task_uid)
    if status != "succeeded":
        print(f"ERROR: Embedder task failed with status: {status}")
        task_info = client.get_task(task.task_uid)
        if hasattr(task_info, "error") and task_info.error:
            print(f"Error details: {task_info.error}")
        sys.exit(1)

    print(f"Embedder '{EMBEDDER_NAME}' configured successfully.")


def verify_embedder(client: meilisearch.Client) -> None:
    index = client.index(MEILISEARCH_INDEX)
    settings = index.get_settings()
    embedders = settings.get("embedders", {}) if isinstance(settings, dict) else {}

    if EMBEDDER_NAME in embedders:
        print(f"Verified: embedder '{EMBEDDER_NAME}' is present in index settings.")
    else:
        print(f"WARNING: embedder '{EMBEDDER_NAME}' not found in settings after setup.")
        print(f"Current embedders: {embedders}")


def main() -> None:
    client = meilisearch.Client(
        MEILISEARCH_HOST,
        MEILISEARCH_API_KEY if MEILISEARCH_API_KEY else None,
    )

    try:
        health = client.health()
        print(f"Meilisearch health: {health}")
    except Exception as e:
        print(f"ERROR: Cannot connect to Meilisearch at {MEILISEARCH_HOST}: {e}")
        sys.exit(1)

    enable_vector_store()
    setup_embedder(client)
    verify_embedder(client)

    print("\nDone. Semantic search is ready on index '{}'.".format(MEILISEARCH_INDEX))


if __name__ == "__main__":
    main()
