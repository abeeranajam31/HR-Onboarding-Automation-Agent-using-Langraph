"""
Retrieval Test Script for HR Onboarding Knowledge Base
Purpose:
- Test semantic search queries against ChromaDB
- Demonstrate metadata filtering (e.g., querying only 'policy' or 'compliance' docs)
"""

import chromadb
from langchain.embeddings import HuggingFaceEmbeddings

# ─────────────────────────────────────────────
# Initialize ChromaDB and embeddings
# ─────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path="output/chroma_db")
collection = chroma_client.get_collection("hr_onboarding_kb")

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# ─────────────────────────────────────────────
# Utility: Perform semantic query
# ─────────────────────────────────────────────
def semantic_query(query_text: str, top_k: int = 3, metadata_filter: dict = None):
    """
    Args:
        query_text: Natural language query string
        top_k: Number of results to return
        metadata_filter: Optional dict to filter by metadata, e.g.,
                         {"doc_type": "policy"} or {"department": "Legal"}
    Returns:
        List of matching chunks with content & metadata
    """
    # Embed the query
    query_embedding = embeddings.embed_query(query_text)

    # Perform ChromaDB query
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=metadata_filter
    )

    # Extract content + metadata for display
    output = []
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        output.append({"content": doc, "metadata": meta})
    return output

# ─────────────────────────────────────────────
# TEST QUERIES
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # 1️⃣ Basic retrieval: "What are the mandatory compliance requirements?"
    print("\n--- Test 1: Basic Compliance Query ---")
    results = semantic_query("What are the mandatory compliance requirements?", top_k=3)
    for i, res in enumerate(results, 1):
        print(f"\nResult {i} (Source: {res['metadata']['source_file']}, Priority: {res['metadata']['priority_level']})")
        print(res['content'][:500], "...")  # print first 500 chars

    # 2️⃣ Metadata filtering: Only from 'organization-coe.pdf' (Ethics & Code of Conduct)
    print("\n--- Test 2: Metadata Filter (Policy Document Only) ---")
    metadata_filter = {"source_file": "organization-coe.pdf"}
    results = semantic_query("Find guidance on ethical decision making", top_k=2, metadata_filter=metadata_filter)
    for i, res in enumerate(results, 1):
        print(f"\nResult {i} (Source: {res['metadata']['source_file']}, Topic: {res['metadata']['topic']})")
        print(res['content'][:500], "...")

    # 3️⃣ Metadata filtering: Only employee records
    print("\n--- Test 3: Metadata Filter (Employee Records Only) ---")
    metadata_filter = {"doc_type": "employee_record"}
    results = semantic_query("Who is joining the HR department?", top_k=3, metadata_filter=metadata_filter)
    for i, res in enumerate(results, 1):
        print(f"\nResult {i} (Employee ID: {res['metadata']['employee_id']}, Role: {res['metadata']['role']})")
        print(res['content'][:500], "...")