from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from local_store import save_index

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
INDEX_PATH = OUTPUT_DIR / "chroma_db" / "local_index.json"

PDF_METADATA_MAP = {
    "2018-shrm-public-policy-issues-guide": {
        "doc_type": "compliance",
        "department": "Legal",
        "priority_level": "high",
        "topic": "labor_law",
        "last_updated": "2018-03-05",
    },
    "organization-coe": {
        "doc_type": "policy",
        "department": "HR",
        "priority_level": "high",
        "topic": "code_of_ethics",
        "last_updated": "2001-01-01",
    },
    "shrm-hr-curriculum-guidelines": {
        "doc_type": "training_guide",
        "department": "Learning_and_Development",
        "priority_level": "medium",
        "topic": "hr_training",
        "last_updated": "2022-01-01",
    },
}


class OnboardingDataIngestor:
    def __init__(self, data_dir: Path = DATA_DIR, output_dir: Path = OUTPUT_DIR):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.chunks: list[dict] = []
        (self.output_dir / "chroma_db").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r"\x0c", " ", text)
        text = re.sub(r"Page\s+\d+", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"https?://\S+|www\.\S+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def split_text(text: str, chunk_size: int = 600, chunk_overlap: int = 80) -> list[str]:
        chunks: list[str] = []
        if not text:
            return chunks
        step = max(1, chunk_size - chunk_overlap)
        start = 0
        while start < len(text):
            chunk = text[start : start + chunk_size]
            if chunk:
                chunks.append(chunk)
            start += step
        return chunks

    def extract_pdf_content(self, pdf_path: Path) -> str:
        reader = PdfReader(str(pdf_path))
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return self.clean_text(full_text)

    @staticmethod
    def _metadata_for_pdf(filename: str) -> dict:
        lowered = filename.lower()
        for key, value in PDF_METADATA_MAP.items():
            if key in lowered:
                return value.copy()
        return {
            "doc_type": "policy",
            "department": "General",
            "priority_level": "medium",
            "topic": "general_hr",
            "last_updated": datetime.now().date().isoformat(),
        }

    def process_policy_documents(self):
        policies_dir = self.data_dir / "policies"
        target_candidates = [
            "2018-shrm-public-policy-issues-guide-030518.pdf",
            "organization-coe.pdf",
            "shrm-hr-curriculum-guidelines-2.pdf",
        ]

        selected = []
        for name in target_candidates:
            path = policies_dir / name
            if path.exists():
                selected.append(path)

        seen_stems = set()
        for pdf_path in selected:
            stem = pdf_path.stem.replace("-2", "").replace("-3", "")
            if stem in seen_stems:
                continue
            seen_stems.add(stem)

            text = self.extract_pdf_content(pdf_path)
            if not text:
                continue

            base_metadata = self._metadata_for_pdf(pdf_path.name)
            for idx, chunk in enumerate(self.split_text(text)):
                if len(chunk) < 50:
                    continue
                self.chunks.append(
                    {
                        "content": chunk,
                        "metadata": {
                            **base_metadata,
                            "source_file": pdf_path.name,
                            "chunk_index": idx,
                            "chunk_id": f"{pdf_path.stem}_{idx}",
                            "ingestion_date": datetime.now().isoformat(),
                        },
                    }
                )

    def process_checklists(self):
        checklist_path = self.data_dir / "checklists" / "onboarding_master.json"
        with open(checklist_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for role, payload in data.get("roles", {}).items():
            for task in payload.get("tasks", []):
                self.chunks.append(
                    {
                        "content": (
                            f"Task: {task['task']}. Role: {role}. Department: {task['department']}. "
                            f"Priority: {task['priority']}. Due-before-start: {task['due_before_start_days']} days."
                        ),
                        "metadata": {
                            "doc_type": "checklist",
                            "department": task["department"],
                            "priority_level": task["priority"],
                            "role": role,
                            "source_file": "onboarding_master.json",
                            "task_id": task["id"],
                            "last_updated": datetime.now().date().isoformat(),
                            "ingestion_date": datetime.now().isoformat(),
                        },
                    }
                )

    def process_employee_data(self):
        with open(self.data_dir / "raw" / "employees.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for row in rows:
            self.chunks.append(
                {
                    "content": (
                        f"Employee {row['first_name']} {row['last_name']} ({row['employee_id']}) is joining as "
                        f"{row['role']} in {row['department']}. Start date: {row['start_date']}. "
                        f"Manager: {row['manager_email']}. Employment: {row['employment_type']}."
                    ),
                    "metadata": {
                        "doc_type": "employee_record",
                        "department": row["department"],
                        "priority_level": "high",
                        "employee_id": str(row["employee_id"]),
                        "role": row["role"],
                        "source_file": "employees.csv",
                        "last_updated": datetime.now().date().isoformat(),
                        "ingestion_date": datetime.now().isoformat(),
                    },
                }
            )

    def load_to_vectordb(self):
        save_index(self.chunks, INDEX_PATH)
        print(f"Loaded {len(self.chunks)} chunks into local vector index at {INDEX_PATH}.")

    def run_pipeline(self):
        if os.getenv("SKIP_PDFS", "0") == "1":
            print("Skipping PDF ingestion (SKIP_PDFS=1).")
        else:
            self.process_policy_documents()
        self.process_checklists()
        self.process_employee_data()
        self.load_to_vectordb()


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ingestor = OnboardingDataIngestor()
    ingestor.run_pipeline()
