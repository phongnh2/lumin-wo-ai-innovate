"""
Import filtered forms from production-form.json into Meilisearch.

Filters:
  - publishedDate is not null/empty
  - amountUsed + initUsed > 200
  - max 1000 documents

Run:
  python scripts/import_forms.py
"""

import json
import os
import sys
import time

import meilisearch

MEILISEARCH_HOST = os.getenv("MEILISEARCH_HOST", "http://localhost:7700")
MEILISEARCH_API_KEY = os.getenv("MEILISEARCH_API_KEY", "")
MEILISEARCH_INDEX = os.getenv("MEILISEARCH_INDEX", "form")

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "production-form.json")

BATCH_SIZE = 100
MAX_DOCS = 1000
TASK_TIMEOUT_S = 120


def build_document(form: dict) -> dict:
    thumbnails = form.get("thumbnails") or []
    thumbnail_url = thumbnails[0]["url"] if thumbnails else None
    file_obj = form.get("file")
    file_url = file_obj["url"] if file_obj else None

    return {
        "id": form["id"],
        "title": form.get("title", ""),
        "subTitle": form.get("subTitle", ""),
        "description": form.get("description", ""),
        "metaTitle": form.get("metaTitle", ""),
        "metaDescription": form.get("metaDescription", ""),
        "metaKeywords": form.get("metaKeywords", ""),
        "slug": form.get("slug", ""),
        "domain": form.get("domain", ""),
        "language": form.get("language", ""),
        "publishedDate": form.get("publishedDate"),
        "ranking": form.get("ranking", 0),
        "templateReleaseId": form.get("templateReleaseId", ""),
        "faqCountry": form.get("faqCountry", ""),
        "faqState": form.get("faqState", ""),
        "countryCode": form.get("countryCode", ""),
        "stateCode": form.get("stateCode", ""),
        "faqPublisher": form.get("faqPublisher", ""),
        "faqSummary": form.get("faqSummary", ""),
        "faqWhoNeedsToFill": form.get("faqWhoNeedsToFill", ""),
        "faqWhereToSubmit": form.get("faqWhereToSubmit", ""),
        "categories": [c["name"] for c in form.get("categories", []) if c.get("name")],
        "amountUsed": form.get("amountUsed", 0),
        "initUsed": form.get("initUsed", 0),
        "totalUsed": (form.get("amountUsed") or 0) + (form.get("initUsed") or 0),
        "thumbnailUrl": thumbnail_url,
        "fileUrl": file_url,
        "pdfUrl": form.get("pdfUrl"),
        "eSignCompatible": form.get("eSignCompatible", False),
        "accessible": form.get("accessible", False),
        "outdated": form.get("outdated", False),
        "publish": form.get("publish", False),
        "internalNotes": json.dumps({
            "thumbnail": thumbnail_url,
            "file": file_url,
        }),
        "publishedAt": form.get("publishedAt"),
        "writerName": form.get("writerName"),
    }


def wait_for_task(client: meilisearch.Client, task_uid: int, timeout: int = TASK_TIMEOUT_S) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get_task(task_uid)
        if task.status in ("succeeded", "failed", "canceled"):
            return task.status
        time.sleep(1)
    raise TimeoutError(f"Task {task_uid} did not complete within {timeout}s")


def ensure_index(client: meilisearch.Client) -> meilisearch.index.Index:
    """Create the index with explicit primary key if it doesn't exist."""
    try:
        existing = client.get_index(MEILISEARCH_INDEX)
        print(f"Index '{MEILISEARCH_INDEX}' already exists (primaryKey={existing.primary_key}).")
        return existing
    except meilisearch.errors.MeilisearchApiError:
        print(f"Creating index '{MEILISEARCH_INDEX}' with primaryKey='id' ...")
        task = client.create_index(MEILISEARCH_INDEX, {"primaryKey": "id"})
        status = wait_for_task(client, task.task_uid)
        if status != "succeeded":
            print(f"ERROR: Index creation failed: {status}")
            sys.exit(1)
        return client.index(MEILISEARCH_INDEX)


def configure_index(index: meilisearch.index.Index, client: meilisearch.Client) -> None:
    print("Configuring index settings...")

    task = index.update_searchable_attributes([
        "title", "subTitle", "description", "metaTitle", "metaDescription",
        "metaKeywords", "faqSummary", "faqPublisher", "faqWhoNeedsToFill",
        "faqWhereToSubmit", "categories", "slug", "domain",
    ])
    wait_for_task(client, task.task_uid)

    task = index.update_filterable_attributes([
        "language", "countryCode", "stateCode", "eSignCompatible",
        "accessible", "outdated", "publish", "publishedDate", "totalUsed",
        "amountUsed", "initUsed", "ranking", "categories",
    ])
    wait_for_task(client, task.task_uid)

    task = index.update_sortable_attributes([
        "ranking", "totalUsed", "publishedDate", "amountUsed",
    ])
    wait_for_task(client, task.task_uid)

    print("Index settings configured.")


def filter_form(form: dict) -> bool:
    if not form.get("publishedDate"):
        return False
    total_used = (form.get("amountUsed") or 0) + (form.get("initUsed") or 0)
    return total_used > 100


def load_and_filter(data_path: str) -> list[dict]:
    print(f"Loading JSON from {data_path} ...")
    with open(data_path, "r", encoding="utf-8") as f:
        all_forms = json.load(f)

    print(f"Total records in file: {len(all_forms)}")

    filtered = []
    for form in all_forms:
        if filter_form(form):
            filtered.append(form)
            if len(filtered) >= MAX_DOCS:
                break

    print(f"Filtered to {len(filtered)} records (publishedDate set + amountUsed+initUsed > 100, max {MAX_DOCS})")
    return filtered


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

    index = ensure_index(client)
    configure_index(index, client)

    forms = load_and_filter(DATA_PATH)
    documents = [build_document(f) for f in forms]

    total = len(documents)
    imported = 0

    for i in range(0, total, BATCH_SIZE):
        batch = documents[i: i + BATCH_SIZE]
        task = index.add_documents(batch, primary_key="id")
        status = wait_for_task(client, task.task_uid)

        if status != "succeeded":
            print(f"ERROR: Batch {i // BATCH_SIZE + 1} failed with status: {status}")
            sys.exit(1)

        imported += len(batch)
        print(f"  Imported {imported}/{total} documents")

    stats = index.get_stats()
    print(f"\nDone. Index '{MEILISEARCH_INDEX}' now has {stats.number_of_documents} documents.")


if __name__ == "__main__":
    main()
