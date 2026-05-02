"""
Data Ingestion Pipeline for HR Onboarding Agent
Processes 3 SHRM PDFs + JSON checklists + CSV employee data

PDFs used:
- 2018-shrm-public-policy-issues-guide-030518.pdf → Compliance & Legal
- organization-coe.pdf → Ethics & Code of Conduct
- shrm-hr-curriculum-guidelines-3.pdf → Training Requirements

Author: HR Onboarding Agent Project
"""

import os
import json
import re
from datetime import datetime
from typing import List, Dict
import pandas as pd
from pypdf import PdfReader
import chromadb

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# HARDCODED METADATA MAP based on actual PDF content
# ─────────────────────────────────────────────
PDF_METADATA_MAP = {
    "2018-shrm-public-policy-issues-guide": {
        "doc_type": "compliance",
        "department": "Legal",
        "priority_level": "high",
        "topic": "labor_law_and_workplace_compliance",
        "subtopics": "background_checks,civil_rights,pay_equity,harassment,immigration",
        "audience": "all_employees",
        "last_updated": "2018-03-05",
        "source_org": "SHRM"
    },
    "organization-coe": {
        "doc_type": "policy",
        "department": "HR",
        "priority_level": "high",
        "topic": "code_of_ethics_and_conduct",
        "subtopics": "ethical_behavior,decision_making,misconduct_reporting,values",
        "audience": "all_employees",
        "last_updated": "2001-01-01",
        "source_org": "Ethics_Resource_Center_SHRM"
    },
    "shrm-hr-curriculum-guidelines": {
        "doc_type": "training_guide",
        "department": "Learning_and_Development",
        "priority_level": "medium",
        "topic": "hr_competencies_and_training_requirements",
        "subtopics": "hr_education,competencies,internships,curriculum,certification",
        "audience": "hr_professionals",
        "last_updated": "2022-01-01",
        "source_org": "SHRM"
    }
}

# Keywords that boost priority to HIGH
HIGH_PRIORITY_KEYWORDS = [
    "required", "must", "mandatory", "compliance", "illegal",
    "violation", "law", "prohibited", "civil rights", "harassment",
    "discrimination", "background check", "security", "immediate",
    "title vii", "eeoc", "fair credit", "penalty"
]

# Keywords that drop priority to LOW
LOW_PRIORITY_KEYWORDS = [
    "optional", "recommended", "suggested", "may choose",
    "appendix", "acknowledgment", "reference", "bibliography"
]


class OnboardingDataIngestor:
    def __init__(self, data_dir: str = "data", output_dir: str = "output"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.chunks = []

        # Create output directory if it doesn't exist
        os.makedirs(f"{output_dir}/chroma_db", exist_ok=True)

        # Initialize ChromaDB (persistent on disk)
        self.chroma_client = chromadb.PersistentClient(
            path=f"{output_dir}/chroma_db"
        )

        # Initialize OpenAI embeddings
        # Initialize local HuggingFace embeddings (runs offline)
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2"
        )
        print("✅ ChromaDB and Embeddings initialized")

    # ─────────────────────────────────────────────
    # TEXT CLEANING
    # ─────────────────────────────────────────────
    def clean_text(self, text: str) -> str:
        """
        Strip noise from PDF-extracted text:
        - Remove page numbers (Page 1, Page 2)
        - Remove SHRM headers/footers that repeat on every page
        - Remove excessive whitespace and newlines
        - Remove PDF form-feed characters
        - Remove URL-only lines
        """
        # Remove form feed characters (PDF page breaks)
        text = re.sub(r'\x0c', ' ', text)

        # Remove repeating SHRM header/footer lines
        text = re.sub(r'SHRM HUMAN RESOURCE CURRICULUM GUIDEBOOK.*?PROGRAMS\s*\d*', '', text)
        text = re.sub(r'2018 SHRM Guide to Public Policy Issues\s*\d*', '', text)
        text = re.sub(r'2017 SHRM Guide to Public Policy Issues\s*\d*', '', text)
        text = re.sub(r'©\d{4}.*?reserved\.', '', text)

        # Remove standalone page numbers
        text = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', text)
        text = re.sub(r'Page \d+', '', text)

        # Remove URLs (but keep context around them)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'www\.\S+', '', text)

        # Remove excessive whitespace and normalize
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    # ─────────────────────────────────────────────
    # PDF EXTRACTION
    # ─────────────────────────────────────────────
    def extract_pdf_content(self, pdf_path: str) -> str:
        """Extract and clean text from PDF file"""
        try:
            reader = PdfReader(pdf_path)
            full_text = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
            return self.clean_text(full_text)
        except Exception as e:
            print(f"  ⚠️  Error reading {pdf_path}: {e}")
            return ""

    # ─────────────────────────────────────────────
    # METADATA HELPERS
    # ─────────────────────────────────────────────
    def _get_pdf_metadata(self, filename: str) -> dict:
        """
        Match filename to hardcoded metadata map.
        Based on actual PDF content analysis.
        """
        filename_lower = filename.lower()
        for key, metadata in PDF_METADATA_MAP.items():
            if key in filename_lower:
                return metadata.copy()

        # Fallback (should not hit for our 3 PDFs)
        return {
            "doc_type": "policy",
            "department": "General",
            "priority_level": "medium",
            "topic": "general_hr",
            "subtopics": "unknown",
            "audience": "all_employees",
            "last_updated": datetime.now().isoformat(),
            "source_org": "SHRM"
        }

    def _infer_chunk_priority(self, content: str) -> str:
        """
        Override base priority per chunk based on content keywords.
        Allows chunk-level priority even within a single document.
        """
        content_lower = content.lower()
        if any(kw in content_lower for kw in HIGH_PRIORITY_KEYWORDS):
            return "high"
        elif any(kw in content_lower for kw in LOW_PRIORITY_KEYWORDS):
            return "low"
        return "medium"

    # ─────────────────────────────────────────────
    # PROCESS PDFs
    # ─────────────────────────────────────────────
    def process_policy_documents(self):
        """
        Process the 3 selected SHRM PDFs with semantic chunking.

        Chunking strategy:
        - chunk_size=600: Large enough to keep a full policy clause or paragraph together
        - chunk_overlap=80: Overlap to avoid splitting related sentences
        - Separators: Try to split at paragraphs first, then sentences
        """
        policies_dir = f"{self.data_dir}/policies"

        if not os.path.exists(policies_dir):
            print(f"  ⚠️  Policies directory not found: {policies_dir}")
            return

        # Only process our 3 target PDFs
        target_pdfs = [
            "2018-shrm-public-policy-issues-guide-030518.pdf",
            "organization-coe.pdf",
            "shrm-hr-curriculum-guidelines-3.pdf"
        ]

        for filename in target_pdfs:
            filepath = os.path.join(policies_dir, filename)

            if not os.path.exists(filepath):
                print(f"  ⚠️  File not found: {filename} — skipping")
                continue

            print(f"  📄 Processing: {filename}")

            # Extract text
            content = self.extract_pdf_content(filepath)

            if not content:
                print(f"  ⚠️  No content extracted from {filename}")
                continue

            # Get base metadata for this document
            base_metadata = self._get_pdf_metadata(filename)

            # Semantic chunking — respect paragraph boundaries
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=600,
                chunk_overlap=80,
                separators=["\n\n", "\n", ". ", "! ", "? ", " "]
            )

            chunks = text_splitter.split_text(content)
            print(f"     → {len(chunks)} chunks created")

            for i, chunk in enumerate(chunks):
                # Skip very short chunks (likely headers/page numbers)
                if len(chunk.strip()) < 50:
                    continue

                # Build per-chunk metadata (inherits from doc + chunk-level priority)
                chunk_metadata = {
                    **base_metadata,
                    "source_file": filename,
                    "chunk_index": i,
                    "chunk_id": f"{filename.replace('.pdf', '')}_{i}",
                    "ingestion_date": datetime.now().isoformat(),
                    # Override priority at chunk level
                    "priority_level": self._infer_chunk_priority(chunk)
                }

                self.chunks.append({
                    "content": chunk,
                    "metadata": chunk_metadata
                })

    # ─────────────────────────────────────────────
    # PROCESS CHECKLISTS
    # ─────────────────────────────────────────────
    def process_checklists(self):
        """
        Process onboarding_master.json.
        Each task becomes one chunk — keeps task data intact (no splitting).
        """
        checklist_path = f"{self.data_dir}/checklists/onboarding_master.json"

        if not os.path.exists(checklist_path):
            print(f"  ⚠️  Checklist not found: {checklist_path}")
            return

        with open(checklist_path, 'r') as f:
            data = json.load(f)

        for role, role_data in data['roles'].items():
            for task in role_data['tasks']:
                # Create human-readable text for embedding
                content = (
                    f"Onboarding Task for {role}: {task['task']}. "
                    f"Handled by {task['department']} department. "
                    f"Priority: {task['priority']}. "
                    f"Must be completed {task['due_before_start_days']} days before employee start date. "
                    f"Estimated time: {task['estimated_time_minutes']} minutes."
                )

                self.chunks.append({
                    "content": content,
                    "metadata": {
                        "doc_type": "checklist",
                        "source_file": "onboarding_master.json",
                        "department": task['department'],
                        "role": role,
                        "task_id": task['id'],
                        "priority_level": task['priority'],
                        "topic": "onboarding_task",
                        "audience": role.lower().replace(" ", "_"),
                        "ingestion_date": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat()
                    }
                })

        print(f"     → {len([c for c in self.chunks if c['metadata'].get('doc_type') == 'checklist'])} checklist chunks created")

    # ─────────────────────────────────────────────
    # PROCESS EMPLOYEE CSV
    # ─────────────────────────────────────────────
    def process_employee_data(self):
        """
        Process employees.csv.
        Each employee row = one chunk (no splitting needed for structured data).
        """
        csv_path = f"{self.data_dir}/raw/employees.csv"

        if not os.path.exists(csv_path):
            print(f"  ⚠️  CSV not found: {csv_path}")
            return

        df = pd.read_csv(csv_path)

        for _, row in df.iterrows():
            content = (
                f"New Employee Record: {row['first_name']} {row['last_name']} "
                f"is joining as a {row['role']} in the {row['department']} department. "
                f"Start date: {row['start_date']}. "
                f"Work location: {row['location']}. "
                f"Employment type: {row['employment_type']}. "
                f"Reports to manager: {row['manager_email']}."
            )

            self.chunks.append({
                "content": content,
                "metadata": {
                    "doc_type": "employee_record",
                    "source_file": "employees.csv",
                    "department": row['department'],
                    "employee_id": str(row['employee_id']),
                    "role": row['role'],
                    "priority_level": "high",
                    "topic": "new_hire_profile",
                    "audience": "hr_coordinator",
                    "ingestion_date": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
            })

        print(f"     → {len(df)} employee records created")

    # ─────────────────────────────────────────────
    # LOAD TO CHROMADB
    # ─────────────────────────────────────────────
    def load_to_vectordb(self):
        """
        Embed all chunks and load into ChromaDB collection.
        Uses OpenAI text-embedding-3-small for vectorization.
        Batches to avoid API rate limits.
        """
        # Delete existing collection to avoid duplicates on re-run
        try:
            self.chroma_client.delete_collection("hr_onboarding_kb")
            print("  🗑️  Deleted existing collection")
        except Exception:
            pass

        # Create fresh collection
        collection = self.chroma_client.create_collection(
            name="hr_onboarding_kb",
            metadata={
                "description": "HR Onboarding Knowledge Base",
                "project": "HR Onboarding Automation Agent",
                "embedding_model": "text-embedding-3-small",
                "created": datetime.now().isoformat()
            }
        )

        print(f"\n  📦 Embedding and loading {len(self.chunks)} chunks...")

        # Prepare data
        documents = [chunk['content'] for chunk in self.chunks]
        metadatas = [chunk['metadata'] for chunk in self.chunks]
        ids = [f"chunk_{i:04d}" for i in range(len(self.chunks))]

        # Generate embeddings in batches (avoid OpenAI rate limits)
        batch_size = 50
        all_embeddings = []

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            print(f"  🔢 Embedding batch {i//batch_size + 1}/{(len(documents)-1)//batch_size + 1}...")
            batch_embeddings = self.embeddings.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)

        # Load into ChromaDB in batches
        for i in range(0, len(documents), batch_size):
            collection.add(
                documents=documents[i:i + batch_size],
                embeddings=all_embeddings[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
                ids=ids[i:i + batch_size]
            )

        print(f"\n  ✅ Successfully loaded {len(self.chunks)} chunks into 'hr_onboarding_kb'")
        print(f"  📊 Collection count: {collection.count()}")

    # ─────────────────────────────────────────────
    # SUMMARY REPORT
    # ─────────────────────────────────────────────
    def print_summary(self):
        """Print breakdown of chunks by source"""
        print("\n" + "="*50)
        print("📊 INGESTION SUMMARY")
        print("="*50)

        by_doc_type = {}
        by_source = {}

        for chunk in self.chunks:
            dt = chunk['metadata']['doc_type']
            sf = chunk['metadata']['source_file']
            by_doc_type[dt] = by_doc_type.get(dt, 0) + 1
            by_source[sf] = by_source.get(sf, 0) + 1

        print("\nBy Document Type:")
        for dt, count in by_doc_type.items():
            print(f"  {dt:25s} → {count} chunks")

        print("\nBy Source File:")
        for sf, count in by_source.items():
            print(f"  {sf:50s} → {count} chunks")

        print(f"\n  TOTAL: {len(self.chunks)} chunks")
        print("="*50)

    # ─────────────────────────────────────────────
    # MAIN PIPELINE
    # ─────────────────────────────────────────────
    def run_pipeline(self):
        """Execute the full ingestion pipeline"""
        print("\n🚀 Starting HR Onboarding Ingestion Pipeline")
        print("="*50)

        print("\n1️⃣  Processing SHRM Policy Documents (3 PDFs)...")
        self.process_policy_documents()

        print("\n2️⃣  Processing Onboarding Checklists (JSON)...")
        self.process_checklists()

        print("\n3️⃣  Processing Employee Records (CSV)...")
        self.process_employee_data()

        self.print_summary()

        print("\n4️⃣  Loading to ChromaDB Vector Database...")
        self.load_to_vectordb()

        print("\n🎉 Pipeline Complete! Knowledge base is ready.")
        print(f"   ChromaDB saved to: output/chroma_db/")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not set!")
        print("   Run: export OPENAI_API_KEY='your-key-here'")
        exit(1)

    ingestor = OnboardingDataIngestor(
        data_dir="data",
        output_dir="output"
    )
    ingestor.run_pipeline()