"""
Import filtered forms from production-form.json into Meilisearch.

Filters:
  - publishedDate is not null/empty
  - amountUsed + initUsed > 100

Run:
  python scripts/import_forms.py
"""

import json
import os
import sys
import time
from datetime import datetime

import meilisearch

MEILISEARCH_HOST = os.getenv("MEILISEARCH_HOST", "http://localhost:7700")
MEILISEARCH_API_KEY = os.getenv("MEILISEARCH_API_KEY", "")
MEILISEARCH_INDEX = os.getenv("MEILISEARCH_INDEX", "form")

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "production-form.json")

BATCH_SIZE = 100
TASK_TIMEOUT_S = 120


def build_category_lookup(all_forms: list) -> dict:
    """Build a map of category_id -> {id, name, slug} from all forms."""
    lookup = {}
    for form in all_forms:
        for cat in form.get("categories") or []:
            cat_id = cat.get("id")
            if cat_id and cat_id not in lookup:
                lookup[cat_id] = {
                    "id": cat_id,
                    "name": cat.get("name", ""),
                    "slug": cat.get("slug", ""),
                }
    return lookup


def build_category(cat: dict, lookup: dict) -> dict:
    parent_id = cat.get("parent")
    parent = None
    if parent_id and isinstance(parent_id, int):
        parent = lookup.get(parent_id, {"id": parent_id, "name": "", "slug": ""})
    return {
        "id": cat.get("id"),
        "name": cat.get("name", ""),
        "slug": cat.get("slug", ""),
        "parent": parent,
    }


def to_array(val) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    return [val]


def parse_published_date_timestamp(date_str) -> int:
    if not date_str:
        return 0
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


def build_document(form: dict, category_lookup: dict) -> dict:
    thumbnails_raw = form.get("thumbnails") or []
    thumbnails = [
        {"url": t.get("url", ""), "alt": t.get("alternativeText")}
        for t in thumbnails_raw
    ]

    file_obj = form.get("file") or {}
    file_data = (
        {
            "id": file_obj.get("id"),
            "name": file_obj.get("name", ""),
            "url": file_obj.get("url", ""),
            "ext": file_obj.get("ext", ""),
            "mime": file_obj.get("mime", ""),
            "size": file_obj.get("size", 0),
        }
        if file_obj
        else None
    )

    categories_raw = form.get("categories") or []
    categories = [build_category(c, category_lookup) for c in categories_raw]

    total_used = (form.get("amountUsed") or 0) + (form.get("initUsed") or 0)
    thumbnail_url = thumbnails[0]["url"] if thumbnails else None
    file_url = file_data["url"] if file_data else None

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
        "publishedDateTimestamp": parse_published_date_timestamp(form.get("publishedDate")),
        "publishedAt": form.get("publishedAt"),
        "ranking": form.get("ranking", 0),
        "countryCode": to_array(form.get("countryCode")),
        "stateCode": to_array(form.get("stateCode")),
        "categories": categories,
        "formTypes": [],
        "searchTerms": form.get("searchTerms") or [],
        "relatedFormByDomain": form.get("relatedFormByDomain") or [],
        "amountUsed": form.get("amountUsed", 0),
        "initUsed": form.get("initUsed", 0),
        "totalUsed": total_used,
        "thumbnails": thumbnails,
        "file": file_data,
        "pdfUrl": form.get("pdfUrl"),
        "eSignCompatible": form.get("eSignCompatible", False),
        "accessible": form.get("accessible", False),
        "outdated": form.get("outdated", False),
        "legalReview": form.get("legalReview"),
        "faqCountry": form.get("faqCountry", ""),
        "faqState": form.get("faqState", ""),
        "faqPublisher": form.get("faqPublisher", ""),
        "faqSummary": form.get("faqSummary", ""),
        "faqWhoNeedsToFill": form.get("faqWhoNeedsToFill", ""),
        "faqWhereToSubmit": form.get("faqWhereToSubmit", ""),
        "writerName": form.get("writerName"),
        "bioLink": form.get("bioLink"),
        "role": form.get("role"),
        "longFormContent": form.get("longFormContent"),
        "internalNotes": json.dumps({"thumbnail": thumbnail_url, "file": file_url}),
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
        "faqWhereToSubmit", "searchTerms", "slug", "domain",
    ])
    wait_for_task(client, task.task_uid)

    task = index.update_filterable_attributes([
        "domain", "language", "outdated", "eSignCompatible", "accessible",
        "legalReview", "publishedDateTimestamp", "publishedDate", "totalUsed",
        "amountUsed", "initUsed", "ranking", "countryCode", "stateCode",
        "categories.id", "categories.slug", "categories.name",
    ])
    wait_for_task(client, task.task_uid)

    task = index.update_sortable_attributes([
        "ranking", "totalUsed", "publishedDate", "publishedDateTimestamp",
        "amountUsed", "outdated", "title",
    ])
    wait_for_task(client, task.task_uid)

    print("Index settings configured.")


def filter_form(form: dict) -> bool:
    return bool(form.get("publishedDate"))


def load_and_filter(data_path: str) -> list:
    print(f"Loading JSON from {data_path} ...")
    with open(data_path, "r", encoding="utf-8") as f:
        all_forms = json.load(f)

    print(f"Total records in file: {len(all_forms)}")

    filtered = [form for form in all_forms if filter_form(form)]

    print(f"Filtered to {len(filtered)} records (publishedDate set)")
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

    all_forms = load_and_filter(DATA_PATH)
    category_lookup = build_category_lookup(all_forms)
    documents = [build_document(f, category_lookup) for f in all_forms]

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
