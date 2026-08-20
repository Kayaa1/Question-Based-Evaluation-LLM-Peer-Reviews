"""Sample human peer reviews from a local NLPeer data tree.

This script is the first data-preparation step. It reads NLPeer ``reviews.json``
files, normalizes each review into one record, and samples by dataset and coarse
score tier for subsequent LLM-assisted open coding.

By default, output is written to ``outputs/``. Git ignores this directory
because sampled review text still comes from the raw dataset and should not be
committed to the repository without careful review.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_DATASETS = [
    # Restrict the main scope to modern NLP/AI peer-review data so annotators
    # with AI/NLP backgrounds can conduct IAA. F1000 is outside the target
    # domain, while COLING and PeerRead are initially excluded from the main
    # checklist-derivation data because their samples are smaller.
    "ARR-22",
    "ARR-EMNLP-24-v1.1",
    "EMNLP23",
]

REPORT_FIELD_ORDER = [
    # Review-form field names differ across venues. This order is used when
    # assembling review_text so summary, strengths, weaknesses, comments, and
    # ethics read more like a complete review. Unlisted fields follow in
    # alphabetical order.
    "main",
    "paper_summary",
    "paper_topic_and_main_contributions",
    "summary_of_strengths",
    "reasons_to_accept",
    "summary_of_weaknesses",
    "reasons_to_reject",
    "comments,_suggestions_and_typos",
    "comments_suggestions_and_typos",
    "questions_for_the_authors",
    "typos_grammar_style_and_presentation_improvements",
    "ethical_concerns",
]


@dataclass
class ReviewRecord:
    dataset: str
    paper_id: str
    version: str
    review_index: int
    review_id: str
    title: str
    abstract: str
    venue_or_cycle: str
    score_proxy_field: str
    score_proxy_raw: str
    score_proxy_value: str
    score_tier: str
    report_fields: str
    review_text: str
    review_word_count: int
    reviewer_present: bool
    source_reviews_path: str


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def normalise_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return re.sub(r"\s+", " ", text).strip()


def combine_report_fields(report: dict[str, Any]) -> tuple[str, str]:
    """Combine a structured review report into readable text and return the fields used."""

    ordered_keys = [key for key in REPORT_FIELD_ORDER if key in report]
    remaining_keys = sorted(key for key in report if key not in ordered_keys)

    sections: list[str] = []
    used_keys: list[str] = []
    for key in ordered_keys + remaining_keys:
        text = normalise_text(report.get(key))
        if not text:
            continue
        sections.append(f"[{key}]\n{text}")
        used_keys.append(key)

    return "\n\n".join(sections), "|".join(used_keys)


def parse_numeric_score(score_text: str) -> float | None:
    """Parse a leading number from strings such as `4 = Strong...` or `4.5`."""

    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)", score_text)
    if not match:
        return None
    return float(match.group(1))


def extract_score_proxy(scores: dict[str, Any]) -> tuple[str, str]:
    """Extract the score proxy used for stratified sampling.

    ARR-22 provides `overall`, and ARR-EMNLP-24 provides
    `overall_assessment`; either can directly serve as a paper/review score-tier
    proxy. EMNLP23 has no overall field, only `soundness`, `excitement`, and
    `reproducibility`. Use mean(soundness, excitement) as a more balanced proxy
    so novelty or interest is not overrepresented by excitement alone. This
    proxy is used only for sampling strata; it is not a gold label.
    """

    for key in ["overall", "overall_assessment", "recommendation"]:
        if key in scores and scores[key] is not None:
            return key, normalise_text(scores[key])

    soundness = parse_numeric_score(normalise_text(scores.get("soundness", "")))
    excitement = parse_numeric_score(normalise_text(scores.get("excitement", "")))
    if soundness is not None and excitement is not None:
        proxy_value = round((soundness + excitement) / 2, 2)
        return "mean(soundness,excitement)", (
            f"{proxy_value} "
            f"(soundness={normalise_text(scores.get('soundness'))}; "
            f"excitement={normalise_text(scores.get('excitement'))})"
        )

    if "excitement" in scores and scores["excitement"] is not None:
        return "excitement", normalise_text(scores["excitement"])

    return "", ""


def assign_score_tier(score_text: str) -> tuple[str, str]:
    """Map a score proxy on a 1--5 scale to low, mid, or high."""

    cleaned = score_text.strip()
    lowered = cleaned.lower()

    numeric_score = parse_numeric_score(cleaned)
    if numeric_score is not None:
        if numeric_score <= 2:
            return str(numeric_score), "low"
        if numeric_score >= 4:
            return str(numeric_score), "high"
        return str(numeric_score), "mid"

    if "reject" in lowered:
        return "", "low"
    if "accept with reservations" in lowered or "approve-with-reservations" in lowered:
        return "", "mid"
    if lowered in {"accept", "approve"} or lowered.startswith("accept "):
        return "", "high"

    return "", "unknown"


def find_venue_or_cycle(dataset: str, paper_meta: dict[str, Any], version_meta: dict[str, Any]) -> str:
    for key in ["accepted_at", "venue", "cycle", "split", "origin_dataset"]:
        value = version_meta.get(key, paper_meta.get(key))
        if value:
            return normalise_text(value)
    return dataset


def make_review_record(
    dataset: str,
    dataset_root: Path,
    reviews_path: Path,
    review_index: int,
    review: dict[str, Any],
) -> ReviewRecord | None:
    """Convert one raw NLPeer review into a normalized ReviewRecord.

    Read paper- and version-level ``meta.json`` files, combine structured report
    fields, extract the overall score, and retain ``source_reviews_path`` for
    tracing the record back to raw data. Skip reviews with no usable text.
    """

    version_dir = reviews_path.parent
    paper_dir = version_dir.parent

    report = review.get("report", {})
    scores = review.get("scores", {})
    if not isinstance(report, dict) or not isinstance(scores, dict):
        return None

    review_text, report_fields = combine_report_fields(report)
    if not review_text:
        return None

    paper_meta = read_json_if_exists(paper_dir / "meta.json")
    version_meta = read_json_if_exists(version_dir / "meta.json")

    title = normalise_text(version_meta.get("title", paper_meta.get("title", "")))
    abstract = normalise_text(version_meta.get("abstract", paper_meta.get("abstract", "")))
    venue_or_cycle = find_venue_or_cycle(dataset, paper_meta, version_meta)

    score_proxy_field, score_proxy_raw = extract_score_proxy(scores)
    score_proxy_value, score_tier = assign_score_tier(score_proxy_raw)

    review_id = normalise_text(review.get("rid", ""))
    review_word_count = len(review_text.split())

    return ReviewRecord(
        dataset=dataset,
        paper_id=paper_dir.name,
        version=version_dir.name,
        review_index=review_index,
        review_id=review_id,
        title=title,
        abstract=abstract,
        venue_or_cycle=venue_or_cycle,
        score_proxy_field=score_proxy_field,
        score_proxy_raw=score_proxy_raw,
        score_proxy_value=score_proxy_value,
        score_tier=score_tier,
        report_fields=report_fields,
        review_text=review_text,
        review_word_count=review_word_count,
        reviewer_present=bool(review.get("reviewer")),
        source_reviews_path=str(reviews_path.relative_to(dataset_root.parent)),
    )


def collect_reviews(nlpeer_root: Path, dataset_names: list[str]) -> list[ReviewRecord]:
    """Collect review records from every `*/v*/reviews.json` in the selected datasets."""

    records: list[ReviewRecord] = []

    for dataset in dataset_names:
        dataset_root = nlpeer_root / dataset
        data_root = dataset_root / "data"
        if not data_root.exists():
            raise FileNotFoundError(f"Missing dataset data directory: {data_root}")

        for reviews_path in sorted(data_root.glob("*/v*/reviews.json")):
            reviews = load_json(reviews_path)
            if not isinstance(reviews, list):
                continue

            for review_index, review in enumerate(reviews):
                if not isinstance(review, dict):
                    continue
                record = make_review_record(
                    dataset=dataset,
                    dataset_root=dataset_root,
                    reviews_path=reviews_path,
                    review_index=review_index,
                    review=review,
                )
                if record is not None:
                    records.append(record)

    return records


def sample_group(records: list[ReviewRecord], target_size: int, rng: random.Random) -> list[ReviewRecord]:
    """Sample as evenly as possible across score tiers within one dataset.

    Rules:
    1. Divide records into low, mid, high, and unknown by `score_tier`.
    2. Allocate target_size evenly among tiers that exist in the dataset.
    3. If a tier is too small, take all its records and fill the shortfall from
       the remaining reviews.

    The default target is 60 reviews per dataset. If low, mid, and high are all
    present, this yields 20 reviews per tier. The tier is only a sampling proxy,
    not the final checklist quality label.
    """

    if len(records) <= target_size:
        return list(records)

    by_tier: dict[str, list[ReviewRecord]] = defaultdict(list)
    for record in records:
        by_tier[record.score_tier].append(record)

    tier_order = ["low", "mid", "high", "unknown"]
    non_empty_tiers = [tier for tier in tier_order if by_tier.get(tier)]
    if not non_empty_tiers:
        return []

    base = target_size // len(non_empty_tiers)
    remainder = target_size % len(non_empty_tiers)

    selected: list[ReviewRecord] = []
    selected_keys: set[tuple[str, str, str, int]] = set()

    for tier_position, tier in enumerate(non_empty_tiers):
        tier_records = by_tier[tier]
        tier_target = base + (1 if tier_position < remainder else 0)
        tier_sample = rng.sample(tier_records, min(tier_target, len(tier_records)))
        for record in tier_sample:
            selected.append(record)
            selected_keys.add((record.dataset, record.paper_id, record.version, record.review_index))

    if len(selected) < target_size:
        remaining = [
            record
            for record in records
            if (record.dataset, record.paper_id, record.version, record.review_index) not in selected_keys
        ]
        selected.extend(rng.sample(remaining, min(target_size - len(selected), len(remaining))))

    return selected


def stratified_sample(
    records: list[ReviewRecord],
    per_dataset: int,
    seed: int,
) -> list[ReviewRecord]:
    """Group records by dataset, then call sample_group for within-dataset stratification."""

    rng = random.Random(seed)

    by_dataset: dict[str, list[ReviewRecord]] = defaultdict(list)
    for record in records:
        by_dataset[record.dataset].append(record)

    sampled: list[ReviewRecord] = []
    for dataset in sorted(by_dataset):
        sampled.extend(sample_group(by_dataset[dataset], per_dataset, rng))

    sampled.sort(key=lambda item: (item.dataset, item.score_tier, item.paper_id, item.version, item.review_index))
    return sampled


def write_csv(records: list[ReviewRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(records[0]).keys()) if records else [field.name for field in ReviewRecord.__dataclass_fields__.values()]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


def write_jsonl(records: list[ReviewRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def build_summary(
    all_records: list[ReviewRecord],
    eligible_records: list[ReviewRecord],
    sampled_records: list[ReviewRecord],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "nlpeer_root": str(Path(args.nlpeer_root).resolve()),
        "datasets": args.datasets,
        "seed": args.seed,
        "per_dataset": args.per_dataset,
        "min_review_words": args.min_review_words,
        "collected_reviews": len(all_records),
        "eligible_reviews": len(eligible_records),
        "sampled_reviews": len(sampled_records),
        "collected_by_dataset": dict(Counter(record.dataset for record in all_records)),
        "eligible_by_dataset": dict(Counter(record.dataset for record in eligible_records)),
        "sampled_by_dataset": dict(Counter(record.dataset for record in sampled_records)),
        "sampled_by_dataset_and_tier": {
            dataset: dict(Counter(record.score_tier for record in sampled_records if record.dataset == dataset))
            for dataset in args.datasets
        },
        "sampled_review_word_count": {
            "min": min((record.review_word_count for record in sampled_records), default=0),
            "max": max((record.review_word_count for record in sampled_records), default=0),
            "mean": round(
                sum(record.review_word_count for record in sampled_records) / len(sampled_records),
                2,
            )
            if sampled_records
            else 0,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample human reviews from local NLPeer data.")
    parser.add_argument("--nlpeer-root", default="data", help="Path to the NLPeer top-level data directory.")
    parser.add_argument(
        "--output-dir",
        default="outputs/sampling",
        help="Output directory for the sample CSV, JSONL, and summary.",
    )
    parser.add_argument("--seed", type=int, default=20260613, help="Random seed for reproducible sampling.")
    parser.add_argument("--per-dataset", type=int, default=60, help="Target number of reviews per dataset.")
    parser.add_argument(
        "--min-review-words",
        type=int,
        default=50,
        help="Minimum review word count for inclusion in the sampling pool.",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=DEFAULT_DATASETS,
        help="Names of the NLPeer dataset directories to sample.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    nlpeer_root = Path(args.nlpeer_root)
    output_dir = Path(args.output_dir)

    all_records = collect_reviews(nlpeer_root, args.datasets)
    eligible_records = [
        record
        for record in all_records
        if record.review_word_count >= args.min_review_words
    ]
    sampled_records = stratified_sample(eligible_records, per_dataset=args.per_dataset, seed=args.seed)

    sample_size = len(sampled_records)
    dataset_slug = "-".join(dataset.replace("-", "").replace("_", "") for dataset in args.datasets)
    file_stem = f"nlpeer_review_sample_{dataset_slug}_n{sample_size}_seed{args.seed}"

    csv_path = output_dir / f"{file_stem}.csv"
    jsonl_path = output_dir / f"{file_stem}.jsonl"
    summary_path = output_dir / f"{file_stem}_summary.json"

    write_csv(sampled_records, csv_path)
    write_jsonl(sampled_records, jsonl_path)

    summary = build_summary(all_records, eligible_records, sampled_records, args)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWrote CSV: {csv_path}")
    print(f"Wrote JSONL: {jsonl_path}")
    print(f"Wrote summary: {summary_path}")


if __name__ == "__main__":
    main()
