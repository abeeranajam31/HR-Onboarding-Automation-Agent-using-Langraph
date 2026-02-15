
HR Onboarding Agent – Retrieval Test

Author: HR Onboarding Agent Project
Purpose: Test semantic retrieval queries on the HR Onboarding Knowledge Base using ChromaDB.
Embeddings: HuggingFaceEmbeddings (from langchain_community.embeddings)

⸻

Imports & Setup

from langchain_community.embeddings import HuggingFaceEmbeddings
import chromadb

# Initialize ChromaDB client and collection
chroma_client = chromadb.PersistentClient(path="output/chroma_db")
collection = chroma_client.get_collection("hr_onboarding_kb")

# Initialize embeddings
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


⸻

Utility Function: Semantic Query

def semantic_query(query_text, top_k=3, metadata_filter=None):
    query_embedding = embeddings.embed_query(query_text)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=metadata_filter
    )
    output = []
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        output.append({"content": doc, "metadata": meta})
    return output


⸻

Test 1 – Basic Compliance Query

Query:

What are the mandatory compliance requirements?

Code:

results = semantic_query("What are the mandatory compliance requirements?", top_k=3)
for res in results:
    print(res['metadata']['source_file'], res['metadata']['priority_level'], res['content'][:300])

Results:

#	Source File	Priority	Content (Preview)
1	organization-coe.pdf	low	“. It will direct your employees to other resources…”
2	organization-coe.pdf	medium	“Guidelines 1. Avoid the acquisition and dissemination of information…”
3	2018-shrm-public-policy-issues-guide-030518.pdf	high	“As of 2009, certain federal contractors must use the employment eligibility verification system…”


⸻

Test 2 – Metadata Filter (Policy Document Only)

Query:

Find guidance on ethical decision making

Metadata Filter:

metadata_filter = {"source_file": "organization-coe.pdf"}

Code:

results = semantic_query(
    "Find guidance on ethical decision making",
    top_k=2,
    metadata_filter=metadata_filter
)
for res in results:
    print(res['metadata']['source_file'], res['metadata']['topic'], res['content'][:300])

Results:

#	Source File	Topic	Content (Preview)
1	organization-coe.pdf	code_of_ethics_and_conduct	“Beyond clarifying gray areas and providing guidance on everything from the simplest of questions…”
2	organization-coe.pdf	code_of_ethics_and_conduct	“How are Codes of Ethics Developed? Before you begin the code development process ask yourself the following…”


⸻

Test 3 – Metadata Filter (Employee Records Only)

Query:

Who is joining the HR department?

Metadata Filter:

metadata_filter = {"doc_type": "employee_record"}

Code:

results = semantic_query(
    "Who is joining the HR department?",
    top_k=3,
    metadata_filter=metadata_filter
)
for res in results:
    print(res['metadata']['employee_id'], res['metadata']['role'], res['content'][:300])

Results:

#	Employee ID	Role	Content (Preview)
1	EMP001	Software Engineer	“New Employee Record: Alice Johnson is joining as a Software Engineer in the Engineering department…”
2	EMP004	Product Manager	“New Employee Record: David Martinez is joining as a Product Manager in the Product department…”
3	EMP003	Software Engineer	“New Employee Record: Carol Davis is joining as a Software Engineer in the Engineering department…”


⸻

✅ Notes:
	•	Test 2 demonstrates metadata filtering to only return chunks from the Ethics & Code of Conduct document.
	•	Test 3 demonstrates metadata filtering for employee records.
	•	Semantic search uses HuggingFace embeddings and ChromaDB persistent vectors.



# HR Onboarding Agent – Retrieval Test

**Author:** HR Onboarding Agent Project  
**Purpose:** Test semantic retrieval queries on the HR Onboarding Knowledge Base using ChromaDB.  
**Embeddings:** HuggingFaceEmbeddings (from `langchain_community.embeddings`)  

