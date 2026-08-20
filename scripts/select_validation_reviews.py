"""Select reviews for the human pilot, formal IAA, and human--LLM comparison.

This script retains the review-level score-tier definitions from the n180
derivation while adding the data-separation rules required for formal
validation: exclude all historical derivation and development papers, select
at most one human review per paper, and require the human review and available
``paper.itg.json`` to belong to the same manuscript version.

The outputs are private selection manifests, not blinded annotator files. After
the paired LLM reviews have been generated, assign randomized
``blind_review_id`` values consistently by ``pair_id``.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sample_nlpeer_reviews import ReviewRecord, collect_reviews


SELECTION_VERSION = "validation_sampling_v0_2"
VALIDATION_DATASETS = ["ARR-22", "ARR-EMNLP-24-v1.1"]
DEFAULT_EXCLUSION_PATHS = [
    "inputs/selection/paper_blacklist_n197.csv",
]
DEFAULT_OUTPUT_DIR = "outputs/validation_sampling"
DATASET_ORDER = {dataset: index for index, dataset in enumerate(VALIDATION_DATASETS)}
TIER_ORDER = {tier: index for index, tier in enumerate(["low", "mid", "high"])}

# Main comparison: 2 datasets x 3 tiers x 8 reviews = 48 papers.
MAIN_QUOTAS = {
    (dataset, tier): 8
    for dataset in VALIDATION_DATASETS
    for tier in ["low", "mid", "high"]
}

# The three human-pilot papers are disjoint from the main comparison and cover low, mid, and high.
PILOT_QUOTAS = {
    ("ARR-22", "high"): 1,
    ("ARR-EMNLP-24-v1.1", "low"): 1,
    ("ARR-EMNLP-24-v1.1", "mid"): 1,
}

# 12 papers = 24 mixed human/LLM reviews; select 2 papers from each dataset-by-tier cell.
IAA_QUOTAS = {
    ("ARR-22", "low"): 2,
    ("ARR-22", "mid"): 2,
    ("ARR-22", "high"): 2,
    ("ARR-EMNLP-24-v1.1", "low"): 2,
    ("ARR-EMNLP-24-v1.1", "mid"): 2,
    ("ARR-EMNLP-24-v1.1", "high"): 2,
}


@dataclass(frozen=True)
class CandidateReview:
    """A human review that passes the validation eligibility checks."""

    review: ReviewRecord
    paper_itg_path: Path
    paper_pdf_path: Path

    @property
    def paper_key(self) -> tuple[str, str]:
        return self.review.dataset, self.review.paper_id

    @property
    def record_id(self) -> str:
        return make_review_record_id(self.review)


def make_review_record_id(review: ReviewRecord) -> str:
    """Build a stable review ID using the existing sample/request pipeline rules."""

    return "::".join(
        [
            review.dataset,
            review.paper_id,
            review.version,
            str(review.review_index),
        ]
    )


def read_paper_blacklist(
    paths: list[Path],
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], set[str]]]:
    """Combine historical samples and selections into a paper-level exclusion blacklist."""

    sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in paths:
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row["dataset"] not in VALIDATION_DATASETS:
                    continue
                sources[(row["dataset"], row["paper_id"])].add(str(path))

    return set(sources), sources


def find_paper_itg_path(review: ReviewRecord, data_root: Path) -> Path | None:
    """Accept only a same-version ITG to avoid human--LLM version confounding."""

    reviews_path = data_root / review.source_reviews_path
    version_dir = reviews_path.parent
    same_version_path = version_dir / "paper.itg.json"
    return same_version_path if same_version_path.exists() else None


def build_candidate_pool(
    records: Iterable[ReviewRecord],
    data_root: Path,
    paper_blacklist: set[tuple[str, str]],
    min_review_words: int,
    min_paper_itg_bytes: int,
) -> tuple[list[CandidateReview], Counter[str]]:
    """Apply review-length, known-tier, paper-exclusion, and ITG-availability rules."""

    candidates: list[CandidateReview] = []
    audit_counts: Counter[str] = Counter()

    for review in records:
        audit_counts["collected_reviews"] += 1

        if review.review_word_count < min_review_words:
            audit_counts["excluded_short_review"] += 1
            continue
        if review.score_tier not in TIER_ORDER:
            audit_counts["excluded_unknown_tier"] += 1
            continue
        if (review.dataset, review.paper_id) in paper_blacklist:
            audit_counts["excluded_blacklisted_paper_review"] += 1
            continue

        paper_itg_path = find_paper_itg_path(review, data_root)
        if paper_itg_path is None:
            audit_counts["excluded_missing_paper_itg"] += 1
            continue
        paper_pdf_path = paper_itg_path.with_name("paper.pdf")
        if not paper_pdf_path.exists():
            audit_counts["excluded_missing_same_version_pdf"] += 1
            continue
        # A few NLPeer ITGs contain only a title and abstract. Although the files
        # exist, they cannot support paper-aware items such as Grounding and
        # Reasoning, so exclude them before formal sampling.
        if paper_itg_path.stat().st_size < min_paper_itg_bytes:
            audit_counts["excluded_incomplete_paper_itg"] += 1
            continue

        candidates.append(
            CandidateReview(
                review=review,
                paper_itg_path=paper_itg_path,
                paper_pdf_path=paper_pdf_path,
            )
        )
        audit_counts["eligible_candidate_reviews"] += 1

    return candidates, audit_counts


def group_candidates_by_cell_and_paper(
    candidates: Iterable[CandidateReview],
) -> dict[tuple[str, str], dict[tuple[str, str], list[CandidateReview]]]:
    """Stratify by dataset/tier, then group by paper to avoid oversampling multi-review papers."""

    grouped: dict[
        tuple[str, str],
        dict[tuple[str, str], list[CandidateReview]],
    ] = defaultdict(lambda: defaultdict(list))

    for candidate in candidates:
        cell = (candidate.review.dataset, candidate.review.score_tier)
        grouped[cell][candidate.paper_key].append(candidate)

    return grouped


def cell_sort_key(
    cell: tuple[str, str],
    grouped: dict[tuple[str, str], dict[tuple[str, str], list[CandidateReview]]],
) -> tuple[int, int, int]:
    """Sample cells with fewer papers first to reduce cross-tier overlap failures."""

    dataset, tier = cell
    return (
        len(grouped.get(cell, {})),
        DATASET_ORDER[dataset],
        TIER_ORDER[tier],
    )


def sample_with_quotas(
    grouped: dict[tuple[str, str], dict[tuple[str, str], list[CandidateReview]]],
    quotas: dict[tuple[str, str], int],
    used_papers: set[tuple[str, str]],
    rng: random.Random,
) -> list[CandidateReview]:
    """Sample to quota while allowing each paper at most once in the full selection."""

    selected: list[CandidateReview] = []
    for cell in sorted(quotas, key=lambda item: cell_sort_key(item, grouped)):
        target = quotas[cell]
        paper_groups = grouped.get(cell, {})
        available_papers = sorted(set(paper_groups) - used_papers)
        rng.shuffle(available_papers)

        if len(available_papers) < target:
            dataset, tier = cell
            raise RuntimeError(
                f"{dataset}/{tier} has only {len(available_papers)} unused candidate papers; "
                f"cannot satisfy quota={target}."
            )

        for paper_key in available_papers[:target]:
            paper_reviews = sorted(paper_groups[paper_key], key=lambda item: item.record_id)
            candidate = rng.choice(paper_reviews)
            selected.append(candidate)
            used_papers.add(paper_key)

    return selected


def select_iaa_subset(
    main_candidates: list[CandidateReview],
    rng: random.Random,
) -> set[str]:
    """Select a 12-paper formal-IAA subset from the main 48 using the predefined matrix."""

    by_cell: dict[tuple[str, str], list[CandidateReview]] = defaultdict(list)
    for candidate in main_candidates:
        cell = (candidate.review.dataset, candidate.review.score_tier)
        by_cell[cell].append(candidate)

    selected_ids: set[str] = set()
    for cell in sorted(IAA_QUOTAS, key=lambda item: (DATASET_ORDER[item[0]], TIER_ORDER[item[1]])):
        candidates = sorted(by_cell[cell], key=lambda item: item.record_id)
        selected = rng.sample(candidates, IAA_QUOTAS[cell])
        selected_ids.update(candidate.record_id for candidate in selected)

    return selected_ids


def path_relative_to_project(path: Path, project_root: Path) -> str:
    """Prefer project-relative output paths so manifests remain interpretable across machines."""

    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path.resolve())


def read_itg_text_stats(path: Path) -> tuple[int, int]:
    """Return ITG node and non-media text-character counts for selected-paper QA."""

    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    if not isinstance(nodes, list):
        return 0, 0

    text_chars = 0
    for node in nodes:
        if not isinstance(node, dict) or node.get("ntype") == "media":
            continue
        content = " ".join(str(node.get("content", "")).split())
        text_chars += len(content)
    return len(nodes), text_chars


def candidate_sort_key(candidate: CandidateReview) -> tuple[int, int, str, str, int]:
    review = candidate.review
    return (
        DATASET_ORDER[review.dataset],
        TIER_ORDER[review.score_tier],
        review.paper_id,
        review.version,
        review.review_index,
    )


def build_manifest_rows(
    candidates: list[CandidateReview],
    pair_prefix: str,
    main_comparison: bool,
    human_pilot: bool,
    iaa_record_ids: set[str],
    selection_seed: int,
    iaa_seed: int,
    data_root: Path,
    project_root: Path,
) -> list[dict[str, object]]:
    """Convert selected candidates into a traceable private selection manifest."""

    rows: list[dict[str, object]] = []
    for pair_number, candidate in enumerate(sorted(candidates, key=candidate_sort_key), start=1):
        review = candidate.review
        review_record_id = candidate.record_id
        pair_id = f"{pair_prefix}_{pair_number:03d}"
        source_reviews_path = data_root / review.source_reviews_path
        itg_node_count, itg_text_chars = read_itg_text_stats(candidate.paper_itg_path)

        rows.append(
            {
                "selection_version": SELECTION_VERSION,
                "pair_id": pair_id,
                "main_comparison": main_comparison,
                "formal_iaa": review_record_id in iaa_record_ids,
                "human_pilot": human_pilot,
                "source_type": "human",
                "review_record_id": review_record_id,
                "dataset": review.dataset,
                "paper_id": review.paper_id,
                "review_version": review.version,
                "review_index": review.review_index,
                "nlpeer_review_id": review.review_id,
                "score_proxy_field": review.score_proxy_field,
                "score_proxy_raw": review.score_proxy_raw,
                "score_proxy_value": review.score_proxy_value,
                "score_tier": review.score_tier,
                "title": review.title,
                "abstract": review.abstract,
                "venue_or_cycle": review.venue_or_cycle,
                "report_fields": review.report_fields,
                "review_text": review.review_text,
                "review_word_count": review.review_word_count,
                "reviewer_present": review.reviewer_present,
                "source_reviews_path": path_relative_to_project(source_reviews_path, project_root),
                "paper_itg_path": path_relative_to_project(candidate.paper_itg_path, project_root),
                "paper_pdf_path": path_relative_to_project(candidate.paper_pdf_path, project_root),
                "paper_context_version": candidate.paper_itg_path.parent.name,
                "paper_itg_size_bytes": candidate.paper_itg_path.stat().st_size,
                "paper_itg_node_count": itg_node_count,
                "paper_itg_text_chars": itg_text_chars,
                "derivation_overlap": False,
                "selection_seed": selection_seed,
                "iaa_seed": iaa_seed,
            }
        )

    return rows


def write_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Cannot write an empty manifest: {path}")

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_overview_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build a lean table for manual review without duplicating long review or abstract text."""

    fields = [
        "pair_id",
        "selection_split",
        "main_comparison",
        "formal_iaa",
        "human_pilot",
        "dataset",
        "paper_id",
        "review_version",
        "review_index",
        "nlpeer_review_id",
        "score_tier",
        "score_proxy_value",
        "title",
        "review_record_id",
        "review_word_count",
        "paper_context_version",
        "paper_itg_path",
        "paper_pdf_path",
        "paper_itg_text_chars",
    ]
    overview_rows: list[dict[str, object]] = []
    for row in rows:
        enriched = dict(row)
        enriched["selection_split"] = "main" if row["main_comparison"] else "human_pilot"
        overview_rows.append({field: enriched[field] for field in fields})
    return overview_rows


def build_blacklist_rows(
    blacklist_sources: dict[tuple[str, str], set[str]],
) -> list[dict[str, object]]:
    """Record the final paper-level blacklist and each paper's exclusion sources."""

    rows: list[dict[str, object]] = []
    for (dataset, paper_id), sources in sorted(blacklist_sources.items()):
        rows.append(
            {
                "dataset": dataset,
                "paper_id": paper_id,
                "exclusion_source_count": len(sources),
                "exclusion_sources": "|".join(sorted(sources)),
            }
        )
    return rows


def nested_counts(rows: Iterable[dict[str, object]]) -> dict[str, dict[str, int]]:
    counts = Counter((str(row["dataset"]), str(row["score_tier"])) for row in rows)
    return {
        dataset: {tier: counts[(dataset, tier)] for tier in ["low", "mid", "high"]}
        for dataset in VALIDATION_DATASETS
    }


def numeric_summary(rows: list[dict[str, object]], field: str) -> dict[str, float | int]:
    values = [int(row[field]) for row in rows]
    return {
        "min": min(values),
        "mean": round(sum(values) / len(values), 2),
        "max": max(values),
    }


def candidate_paper_counts(
    grouped: dict[tuple[str, str], dict[tuple[str, str], list[CandidateReview]]],
) -> dict[str, dict[str, int]]:
    return {
        dataset: {
            tier: len(grouped.get((dataset, tier), {}))
            for tier in ["low", "mid", "high"]
        }
        for dataset in VALIDATION_DATASETS
    }


def validate_selection(
    main_rows: list[dict[str, object]],
    pilot_rows: list[dict[str, object]],
    paper_blacklist: set[tuple[str, str]],
) -> dict[str, bool]:
    """Enforce count, distribution, paper-uniqueness, and historical-leakage checks."""

    all_rows = main_rows + pilot_rows
    main_papers = {(str(row["dataset"]), str(row["paper_id"])) for row in main_rows}
    pilot_papers = {(str(row["dataset"]), str(row["paper_id"])) for row in pilot_rows}
    all_record_ids = [str(row["review_record_id"]) for row in all_rows]
    iaa_rows = [row for row in main_rows if row["formal_iaa"]]

    checks = {
        "main_has_48_rows": len(main_rows) == 48,
        "main_has_48_unique_papers": len(main_papers) == 48,
        "pilot_has_3_rows": len(pilot_rows) == 3,
        "pilot_has_3_unique_papers": len(pilot_papers) == 3,
        "main_and_pilot_papers_are_disjoint": main_papers.isdisjoint(pilot_papers),
        "all_review_record_ids_are_unique": len(all_record_ids) == len(set(all_record_ids)),
        "no_blacklisted_paper_overlap": not (main_papers | pilot_papers) & paper_blacklist,
        "all_selected_papers_have_itg": all(bool(row["paper_itg_path"]) for row in all_rows),
        "all_selected_papers_have_same_version_pdf": all(
            bool(row["paper_pdf_path"]) for row in all_rows
        ),
        "all_review_and_paper_versions_match": all(
            row["review_version"] == row["paper_context_version"] for row in all_rows
        ),
        "all_selected_papers_have_substantive_itg_text": all(
            int(row["paper_itg_text_chars"]) >= 5_000 for row in all_rows
        ),
        "formal_iaa_has_12_papers": len(iaa_rows) == 12,
        "formal_iaa_is_subset_of_main": all(bool(row["main_comparison"]) for row in iaa_rows),
        "main_cell_counts_are_eight": all(
            count == 8
            for dataset_counts in nested_counts(main_rows).values()
            for count in dataset_counts.values()
        ),
    }

    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Selection integrity checks failed: {failed}")
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select held-out human reviews for validation.")
    parser.add_argument("--nlpeer-root", default="data")
    parser.add_argument(
        "--exclusion-paths",
        nargs="+",
        default=DEFAULT_EXCLUSION_PATHS,
        help="Historical sample or selection CSV files to exclude at the paper level.",
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-review-words", type=int, default=50)
    parser.add_argument(
        "--min-paper-itg-bytes",
        type=int,
        default=10_000,
        help="Exclude clearly incomplete paper.itg.json files containing only a title or abstract.",
    )
    parser.add_argument("--seed", type=int, default=20260717, help="Main/pilot selection seed.")
    parser.add_argument("--iaa-seed", type=int, default=20260718, help="Formal-IAA subset seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    data_root = Path(args.nlpeer_root)
    exclusion_paths = [Path(path) for path in args.exclusion_paths]
    output_dir = Path(args.output_dir)

    paper_blacklist, blacklist_sources = read_paper_blacklist(exclusion_paths)
    all_records = collect_reviews(data_root, VALIDATION_DATASETS)
    candidate_pool, pool_audit = build_candidate_pool(
        all_records,
        data_root=data_root,
        paper_blacklist=paper_blacklist,
        min_review_words=args.min_review_words,
        min_paper_itg_bytes=args.min_paper_itg_bytes,
    )
    grouped = group_candidates_by_cell_and_paper(candidate_pool)

    selection_rng = random.Random(args.seed)
    used_papers: set[tuple[str, str]] = set()
    main_candidates = sample_with_quotas(grouped, MAIN_QUOTAS, used_papers, selection_rng)
    pilot_candidates = sample_with_quotas(grouped, PILOT_QUOTAS, used_papers, selection_rng)
    iaa_record_ids = select_iaa_subset(main_candidates, random.Random(args.iaa_seed))

    main_rows = build_manifest_rows(
        main_candidates,
        pair_prefix="PAIR",
        main_comparison=True,
        human_pilot=False,
        iaa_record_ids=iaa_record_ids,
        selection_seed=args.seed,
        iaa_seed=args.iaa_seed,
        data_root=data_root,
        project_root=project_root,
    )
    pilot_rows = build_manifest_rows(
        pilot_candidates,
        pair_prefix="PILOT_PAIR",
        main_comparison=False,
        human_pilot=True,
        iaa_record_ids=set(),
        selection_seed=args.seed,
        iaa_seed=args.iaa_seed,
        data_root=data_root,
        project_root=project_root,
    )
    integrity_checks = validate_selection(main_rows, pilot_rows, paper_blacklist)

    stem = f"{SELECTION_VERSION}_seed{args.seed}"
    main_path = output_dir / f"{stem}_main_n48.csv"
    pilot_path = output_dir / f"{stem}_human_pilot_n3.csv"
    iaa_path = output_dir / f"{stem}_formal_iaa_human_n12.csv"
    all_path = output_dir / f"{stem}_all_n51.csv"
    overview_path = output_dir / f"{stem}_overview_n51.csv"
    blacklist_path = output_dir / f"{stem}_paper_blacklist_n{len(paper_blacklist)}.csv"
    summary_path = output_dir / f"{stem}_summary.json"

    iaa_rows = [row for row in main_rows if row["formal_iaa"]]
    write_csv(main_rows, main_path)
    write_csv(pilot_rows, pilot_path)
    write_csv(iaa_rows, iaa_path)
    write_csv(main_rows + pilot_rows, all_path)
    write_csv(build_overview_rows(main_rows + pilot_rows), overview_path)
    write_csv(build_blacklist_rows(blacklist_sources), blacklist_path)

    summary = {
        "selection_version": SELECTION_VERSION,
        "created_for": ["human_pilot", "formal_iaa", "human_llm_comparison"],
        "datasets": VALIDATION_DATASETS,
        "score_tier_unit": "selected human review",
        "score_tier_boundaries": {"low": "<= 2", "mid": "> 2 and < 4", "high": ">= 4"},
        "min_review_words": args.min_review_words,
        "min_paper_itg_bytes": args.min_paper_itg_bytes,
        "selection_seed": args.seed,
        "iaa_seed": args.iaa_seed,
        "exclusion_paths": [path_relative_to_project(path, project_root) for path in exclusion_paths],
        "blacklisted_unique_papers": len(paper_blacklist),
        "blacklisted_unique_papers_by_dataset": dict(
            Counter(dataset for dataset, _paper_id in paper_blacklist)
        ),
        "pool_audit": dict(pool_audit),
        "eligible_unique_candidate_papers_by_dataset_and_tier": candidate_paper_counts(grouped),
        "main": {
            "human_reviews": len(main_rows),
            "unique_papers": len({(row["dataset"], row["paper_id"]) for row in main_rows}),
            "by_dataset_and_tier": nested_counts(main_rows),
        },
        "human_pilot": {
            "human_reviews": len(pilot_rows),
            "unique_papers": len({(row["dataset"], row["paper_id"]) for row in pilot_rows}),
            "by_dataset_and_tier": nested_counts(pilot_rows),
        },
        "formal_iaa_subset": {
            "papers": len(iaa_rows),
            "expected_mixed_reviews_after_llm_generation": len(iaa_rows) * 2,
            "by_dataset_and_tier": nested_counts(iaa_rows),
        },
        "selected_input_quality": {
            "review_word_count": numeric_summary(main_rows + pilot_rows, "review_word_count"),
            "paper_itg_size_bytes": numeric_summary(main_rows + pilot_rows, "paper_itg_size_bytes"),
            "paper_itg_node_count": numeric_summary(main_rows + pilot_rows, "paper_itg_node_count"),
            "paper_itg_text_chars": numeric_summary(main_rows + pilot_rows, "paper_itg_text_chars"),
        },
        "integrity_checks": integrity_checks,
        "outputs": {
            "main_manifest": path_relative_to_project(main_path, project_root),
            "human_pilot_manifest": path_relative_to_project(pilot_path, project_root),
            "formal_iaa_human_manifest": path_relative_to_project(iaa_path, project_root),
            "combined_manifest": path_relative_to_project(all_path, project_root),
            "selection_overview": path_relative_to_project(overview_path, project_root),
            "paper_blacklist": path_relative_to_project(blacklist_path, project_root),
        },
        "blinding_note": (
            "blind_review_id is intentionally deferred until paired LLM reviews exist; "
            "annotator-facing files must not expose source_type, pair_id, score tier, or IAA flags."
        ),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nMain manifest: {main_path}")
    print(f"Human pilot manifest: {pilot_path}")
    print(f"Formal IAA human manifest: {iaa_path}")
    print(f"Combined manifest: {all_path}")
    print(f"Selection overview: {overview_path}")
    print(f"Paper blacklist: {blacklist_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
