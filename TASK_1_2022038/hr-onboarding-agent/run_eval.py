from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from statistics import mean

from secured_graph import run_query

PROJECT_ROOT = Path(__file__).resolve().parent


def _tokenize(text: str) -> set[str]:
    return {t.strip(".,:;!?()[]{}").lower() for t in text.split() if t.strip()}


def _keyword_hit_rate(answer: str, keywords: list[str]) -> float:
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits / max(len(keywords), 1)


def _expected_tool_for_query(query: str) -> str:
    lower = query.lower()
    if any(term in lower for term in ("delete the database", "ignore all previous instructions", "pretend you are")):
        return "BLOCKED"
    if "risk" in lower:
        return "calculate_onboarding_risk"
    if "day 1" in lower or "day-1" in lower or "readiness" in lower:
        return "evaluate_day1_readiness"
    if "status" in lower or "profile" in lower:
        return "get_employee_onboarding_status"
    if "checklist" in lower or "generate" in lower:
        return "generate_onboarding_checklist"
    return "search_onboarding_knowledge"


def _tool_call_accuracy(query: str, response: str, expected_tool: str) -> float:
    if expected_tool == "BLOCKED":
        return 1.0 if "blocked by security guardrails" in response.lower() else 0.0
    actual_tool = _expected_tool_for_query(query)
    return 1.0 if actual_tool == expected_tool else 0.0


def _faithfulness(response: str, expected_keywords: list[str], blocked: bool) -> float:
    if blocked:
        return 1.0 if "blocked by security guardrails" in response.lower() else 0.0
    return _keyword_hit_rate(response, expected_keywords)


def _relevancy(query: str, response: str) -> float:
    q = _tokenize(query)
    a = _tokenize(response)
    return len(q & a) / max(len(q), 1)


def _load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _require_credentials_if_requested() -> None:
    if os.getenv("REQUIRE_CREDENTIALS", "0") != "1":
        return

    required = ["OPENAI_API_KEY"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(f"Missing required environment credentials: {', '.join(missing)}")
        sys.exit(1)


def main() -> None:
    _require_credentials_if_requested()

    dataset_path = Path(os.getenv("TEST_DATASET_PATH", PROJECT_ROOT / "test_dataset.json"))
    thresholds_path = Path(os.getenv("EVAL_THRESHOLDS_PATH", PROJECT_ROOT / "eval_thresholds.json"))
    results_path = Path(os.getenv("EVAL_RESULTS_PATH", PROJECT_ROOT / "output" / "eval_results.json"))

    dataset = _load_json(dataset_path)
    thresholds = _load_json(thresholds_path)

    faithfulness_scores = []
    relevancy_scores = []
    tool_scores = []
    case_rows = []

    for case in dataset:
        result = run_query(case["query"])
        final_answer = result["messages"][-1].content
        blocked = bool(case.get("blocked"))

        faithfulness = _faithfulness(final_answer, case.get("expected_keywords", []), blocked)
        relevancy = _relevancy(case["query"], final_answer)
        tool_accuracy = _tool_call_accuracy(case["query"], final_answer, case["expected_tool"])

        faithfulness_scores.append(faithfulness)
        relevancy_scores.append(relevancy)
        tool_scores.append(tool_accuracy)

        case_rows.append(
            {
                "query": case["query"],
                "expected_tool": case["expected_tool"],
                "faithfulness": round(faithfulness, 3),
                "relevancy": round(relevancy, 3),
                "tool_accuracy": round(tool_accuracy, 3),
            }
        )

    metric_scores = {
        "faithfulness": round(mean(faithfulness_scores), 3) if faithfulness_scores else 0.0,
        "relevancy": round(mean(relevancy_scores), 3) if relevancy_scores else 0.0,
        "tool_accuracy": round(mean(tool_scores), 3) if tool_scores else 0.0,
    }

    metrics = []
    all_pass = True
    for metric_name, threshold in thresholds.items():
        score = metric_scores.get(metric_name, 0.0)
        passed = score >= float(threshold)
        all_pass = all_pass and passed
        metrics.append(
            {
                "name": metric_name,
                "score": score,
                "threshold": float(threshold),
                "pass": passed,
            }
        )

    payload = {
        "dataset_path": str(dataset_path),
        "thresholds_path": str(thresholds_path),
        "results_summary": {"pass": all_pass, "metrics": metrics},
        "all_metric_scores": metric_scores,
        "cases": case_rows,
    }

    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    for metric in metrics:
        print(
            f"{metric['name']}: score={metric['score']} "
            f"threshold={metric['threshold']} pass={metric['pass']}"
        )
    print(f"Results file: {results_path}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
