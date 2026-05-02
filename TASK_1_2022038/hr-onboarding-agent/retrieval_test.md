# Retrieval Test

## Test 1: Basic Compliance Query

Query: `What are the mandatory compliance requirements?`

Expected: top compliance/policy chunks from the PDF knowledge base.

## Test 2: Metadata Filter

Query: `Find guidance on ethical decision making`

Filter: `{"source_file": "organization-coe.pdf"}`

Expected: only results from the ethics and conduct document.

## Test 3: Employee Records

Query: `Who is joining engineering?`

Filter: `{"doc_type": "employee_record"}`

Expected: employee profile chunks for engineering hires.
