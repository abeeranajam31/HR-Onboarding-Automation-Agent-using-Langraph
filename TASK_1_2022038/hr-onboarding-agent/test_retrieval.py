"""Lab 2 retrieval validation with metadata filtering."""

from __future__ import annotations

from pathlib import Path

from local_store import query_index

INDEX_PATH = Path("output/chroma_db/local_index.json")


def semantic_query(query: str, top_k: int = 3, metadata_filter: dict | None = None):
    rows = query_index(path=INDEX_PATH, query=query, top_k=top_k, metadata_filter=metadata_filter)
    return [(row["content"], row["metadata"]) for row in rows]


if __name__ == "__main__":
    print("\n--- Test 1: Basic Compliance Query ---")
    for i, (doc, meta) in enumerate(
        semantic_query("What are the mandatory compliance requirements?", top_k=3), start=1
    ):
        print(f"{i}. {meta['source_file']} | {meta['doc_type']} | {doc[:200]}...")

    print("\n--- Test 2: Metadata Filter (source_file=organization-coe.pdf) ---")
    for i, (doc, meta) in enumerate(
        semantic_query(
            "Find guidance on ethical decision making",
            top_k=2,
            metadata_filter={"source_file": "organization-coe.pdf"},
        ),
        start=1,
    ):
        print(f"{i}. {meta['source_file']} | {meta['topic']} | {doc[:200]}...")

    print("\n--- Test 3: Metadata Filter (doc_type=employee_record) ---")
    for i, (doc, meta) in enumerate(
        semantic_query("Who is joining engineering?", top_k=3, metadata_filter={"doc_type": "employee_record"}),
        start=1,
    ):
        print(f"{i}. {meta['employee_id']} | {meta['role']} | {doc[:200]}...")
