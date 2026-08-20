"""Validate zero-shot generated reviews and export a table for paired analysis."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_RESULT_PATH = (
    "outputs/review_generation/results/"
    "validation_sampling_v0_2_seed20260717_human_pilot_n3_"
    "zero_shot_review_generation_v0_6_pdf_n3_requests_results_gpt-5.4_temp0.0.jsonl"
)
DEFAULT_OUTPUT_DIR = "outputs/review_generation/analysis"
LEGACY_REQUIRED_KEYS = [
    "generation_id",
    "paper_summary",
    "strengths",
    "weaknesses",
    "questions_and_suggestions",
]
NLPEER_FORM_KEYS = [
    "paper_summary",
    "summary_of_strengths",
    "summary_of_weaknesses",
    "comments_suggestions_and_typos",
    "ethical_concerns",
]
V0_5_SECTION_BUDGETS = {
    "paper_summary": 60,
    "summary_of_strengths": 90,
    "summary_of_weaknesses": 140,
    "comments_suggestions_and_typos": 80,
    "ethical_concerns": 30,
}
V0_6_SECTION_BUDGETS = {
    "paper_summary": 60,
    "summary_of_strengths": 90,
    "summary_of_weaknesses": 160,
    "comments_suggestions_and_typos": 90,
    "ethical_concerns": 35,
}
V0_4_SECTION_BUDGETS = {
    "paper_summary": {"max_items": 1, "max_words_per_item": 60},
    "strengths": {"max_items": 3, "max_words_per_item": 35},
    "weaknesses": {"max_items": 3, "max_words_per_item": 45},
    "questions_and_suggestions": {"max_items": 2, "max_words_per_item": 35},
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def normalise_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return [" ".join(item.split()) for item in value if item.strip()]


def format_legacy_review(parsed: dict[str, Any]) -> str:
    strengths = normalise_list(parsed["strengths"]) or []
    weaknesses = normalise_list(parsed["weaknesses"]) or []
    suggestions = normalise_list(parsed["questions_and_suggestions"]) or []

    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- None identified."

    return (
        "[paper_summary]\n"
        f"{' '.join(str(parsed['paper_summary']).split())}\n\n"
        "[summary_of_strengths]\n"
        f"{bullets(strengths)}\n\n"
        "[summary_of_weaknesses]\n"
        f"{bullets(weaknesses)}\n\n"
        "[comments_suggestions_and_questions]\n"
        f"{bullets(suggestions)}"
    )


def format_nlpeer_review(parsed: dict[str, Any]) -> str:
    sections = [
        ("paper_summary", parsed["paper_summary"]),
        ("summary_of_strengths", parsed["summary_of_strengths"]),
        ("summary_of_weaknesses", parsed["summary_of_weaknesses"]),
        ("comments_suggestions_and_typos", parsed["comments_suggestions_and_typos"]),
    ]
    if parsed["ethical_concerns"].strip():
        sections.append(("ethical_concerns", parsed["ethical_concerns"]))
    return "\n\n".join(f"[{name}]\n{str(value).strip()}" for name, value in sections)


def validate_result(result: dict[str, Any]) -> tuple[list[str], list[str], str | None]:
    errors: list[str] = []
    warnings: list[str] = []
    parsed = result.get("parsed_output_json")
    if not isinstance(parsed, dict):
        return [f"parse_error: {result.get('parse_error') or 'missing parsed object'}"], [], None

    prompt_version = result.get("prompt_version")
    is_nlpeer_form = prompt_version in {
        "zero_shot_review_generation_v0_5",
        "zero_shot_review_generation_v0_6",
    }
    required_keys = ["generation_id", *NLPEER_FORM_KEYS] if is_nlpeer_form else LEGACY_REQUIRED_KEYS
    missing = [key for key in required_keys if key not in parsed]
    if missing:
        errors.append(f"missing_keys={missing}")
    if not isinstance(parsed.get("generation_id"), str):
        errors.append("generation_id_not_string")
    elif parsed["generation_id"] != result["source"]["generation_id"]:
        errors.append("generation_id_mismatch")
    if not isinstance(parsed.get("paper_summary"), str) or not parsed.get("paper_summary", "").strip():
        errors.append("paper_summary_invalid")
    if is_nlpeer_form:
        for key in NLPEER_FORM_KEYS:
            if not isinstance(parsed.get(key), str):
                errors.append(f"{key}_not_string")
        for key in ["summary_of_strengths", "summary_of_weaknesses"]:
            if isinstance(parsed.get(key), str) and not parsed[key].strip():
                errors.append(f"{key}_empty")
    else:
        for key in ["strengths", "weaknesses", "questions_and_suggestions"]:
            if normalise_list(parsed.get(key)) is None:
                errors.append(f"{key}_not_string_array")

    if prompt_version == "zero_shot_review_generation_v0_4" and not errors:
        summary_words = word_count(parsed["paper_summary"])
        if summary_words > V0_4_SECTION_BUDGETS["paper_summary"]["max_words_per_item"]:
            errors.append(f"paper_summary_over_budget={summary_words}")
        for key in ["strengths", "weaknesses", "questions_and_suggestions"]:
            values = normalise_list(parsed[key]) or []
            budget = V0_4_SECTION_BUDGETS[key]
            if len(values) > budget["max_items"]:
                errors.append(f"{key}_too_many_items={len(values)}")
            over_budget = [word_count(value) for value in values if word_count(value) > budget["max_words_per_item"]]
            if over_budget:
                errors.append(f"{key}_item_words_over_budget={over_budget}")

    if is_nlpeer_form and not errors:
        section_budgets = (
            V0_6_SECTION_BUDGETS
            if prompt_version == "zero_shot_review_generation_v0_6"
            else V0_5_SECTION_BUDGETS
        )
        for key, max_words in section_budgets.items():
            section_words = word_count(parsed[key])
            if section_words > max_words:
                warnings.append(f"{key}_over_budget={section_words}")

    if errors:
        review_text = None
    elif is_nlpeer_form:
        review_text = format_nlpeer_review(parsed)
    else:
        review_text = format_legacy_review(parsed)
    return errors, warnings, review_text


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize zero-shot generated peer reviews."
    )
    parser.add_argument("--result-path", default=DEFAULT_RESULT_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-words", type=int, default=250)
    parser.add_argument("--max-words", type=int, default=425)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_path = Path(args.result_path)
    output_dir = Path(args.output_dir)
    results = read_jsonl(result_path)
    if not results:
        raise ValueError("Result JSONL is empty.")

    rows: list[dict[str, Any]] = []
    schema_valid_count = 0
    for result in results:
        errors, warnings, generated_review_text = validate_result(result)
        valid = not errors and generated_review_text is not None
        schema_valid_count += int(valid)
        parsed = result.get("parsed_output_json")
        if (
            isinstance(parsed, dict)
            and result.get("prompt_version") in {
                "zero_shot_review_generation_v0_5",
                "zero_shot_review_generation_v0_6",
            }
        ):
            generated_words = sum(word_count(str(parsed.get(key, ""))) for key in NLPEER_FORM_KEYS)
        else:
            generated_words = word_count(generated_review_text or "")
        source = result["source"]
        rows.append(
            {
                "generation_id": source["generation_id"],
                "pair_id": source["pair_id"],
                "dataset": source["dataset"],
                "paper_id": source["paper_id"],
                "paper_version": source["paper_version"],
                "paper_input_mode": source.get("paper_input_mode", "itg_text"),
                "human_review_record_id": source["human_review_record_id"],
                "prompt_version": result["prompt_version"],
                "model_requested": result["model_requested"],
                "model_returned": result.get("model_returned") or "",
                "temperature_requested": result["temperature_requested"],
                "temperature_sent": result["temperature_sent"],
                "created_at_utc": result["created_at_utc"],
                "paper_itg_sha256": source["paper_itg_sha256"],
                "paper_pdf_sha256": source.get("paper_pdf_sha256", ""),
                "paper_input_sha256": source.get("paper_input_sha256", ""),
                "paper_input_bytes": source.get("paper_input_bytes", ""),
                "paper_input_truncated": source.get("paper_input_truncated", False),
                "paper_text_sha256": source.get("paper_text_sha256") or "",
                "paper_text_chars": source.get("paper_text_chars", 0),
                "schema_valid": valid,
                "validation_errors": "|".join(errors),
                "validation_warnings": "|".join(warnings),
                "generated_review_word_count": generated_words,
                "within_target_word_range": args.min_words <= generated_words <= args.max_words,
                "decision_language_detected": bool(
                    re.search(
                        r"\b(?:strong accept|weak accept|strong reject|weak reject|"
                        r"acceptance recommendation|rejection recommendation)\b",
                        generated_review_text or "",
                        flags=re.IGNORECASE,
                    )
                ),
                "generated_review_text": generated_review_text or "",
                "paper_summary": (
                    result["parsed_output_json"].get("paper_summary", "")
                    if isinstance(result.get("parsed_output_json"), dict)
                    else ""
                ),
                "summary_of_strengths": (
                    result["parsed_output_json"].get("summary_of_strengths", "")
                    if isinstance(result.get("parsed_output_json"), dict)
                    else ""
                ),
                "summary_of_weaknesses": (
                    result["parsed_output_json"].get("summary_of_weaknesses", "")
                    if isinstance(result.get("parsed_output_json"), dict)
                    else ""
                ),
                "comments_suggestions_and_typos": (
                    result["parsed_output_json"].get("comments_suggestions_and_typos", "")
                    if isinstance(result.get("parsed_output_json"), dict)
                    else ""
                ),
                "ethical_concerns": (
                    result["parsed_output_json"].get("ethical_concerns", "")
                    if isinstance(result.get("parsed_output_json"), dict)
                    else ""
                ),
                "strengths_json": json.dumps(
                    result["parsed_output_json"].get("strengths", []), ensure_ascii=False
                ) if isinstance(result.get("parsed_output_json"), dict) else "[]",
                "weaknesses_json": json.dumps(
                    result["parsed_output_json"].get("weaknesses", []), ensure_ascii=False
                ) if isinstance(result.get("parsed_output_json"), dict) else "[]",
                "questions_and_suggestions_json": json.dumps(
                    result["parsed_output_json"].get("questions_and_suggestions", []),
                    ensure_ascii=False,
                ) if isinstance(result.get("parsed_output_json"), dict) else "[]",
            }
        )

    output_stem = result_path.stem
    reviews_path = output_dir / f"{output_stem}_reviews.csv"
    summary_path = output_dir / f"{output_stem}_summary.json"
    write_csv(rows, reviews_path)

    valid_word_counts = [
        int(row["generated_review_word_count"]) for row in rows if row["schema_valid"]
    ]
    summary = {
        "result_path": str(result_path),
        "reviews_path": str(reviews_path),
        "results": len(results),
        "parsed_json_count": sum(result.get("parsed_output_json") is not None for result in results),
        "schema_valid_count": schema_valid_count,
        "parse_or_schema_error_count": len(results) - schema_valid_count,
        "target_word_range": [args.min_words, args.max_words],
        "within_target_word_range_count": sum(
            bool(row["within_target_word_range"]) for row in rows
        ),
        "decision_language_detected_count": sum(
            bool(row["decision_language_detected"]) for row in rows
        ),
        "generated_review_word_count": {
            "min": min(valid_word_counts) if valid_word_counts else None,
            "mean": round(mean(valid_word_counts), 2) if valid_word_counts else None,
            "max": max(valid_word_counts) if valid_word_counts else None,
        },
        "all_paper_inputs_untruncated": all(
            not bool(row["paper_input_truncated"]) for row in rows
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
