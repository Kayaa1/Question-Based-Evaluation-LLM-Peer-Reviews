"""Build a human spot-check sample for LLM-assisted concept grouping.

A robust manual review should go beyond a handful of random examples. Include
at least a small representative sample for every global concept, then add
low-confidence assignments and concepts associated with known failure modes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_ASSIGNMENTS_PATH = (
    "outputs/open_coding/concept_grouping/analysis/"
    "open_coding_v0_1_n180_concept_grouping_v0_1_llm_assignments.csv"
)
DEFAULT_LOCAL_TO_GLOBAL_PATH = (
    "outputs/open_coding/concept_grouping/analysis/"
    "open_coding_v0_1_n180_concept_consolidation_v0_1_local_to_global.csv"
)
DEFAULT_GLOBAL_SUMMARY_PATH = (
    "outputs/open_coding/concept_grouping/analysis/"
    "open_coding_v0_1_n180_concept_consolidation_v0_1_global_summary.csv"
)
DEFAULT_OUTPUT_PATH = (
    "outputs/open_coding/concept_grouping/analysis/"
    "open_coding_v0_1_n180_concept_spotcheck_sample_lean.csv"
)


def sample_per_group(df: pd.DataFrame, group_col: str, n: int, seed: int) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    samples = [
        group.sample(n=min(n, len(group)), random_state=seed)
        for _, group in df.groupby(group_col, sort=False)
    ]
    return pd.concat(samples, ignore_index=True) if samples else df.head(0).copy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the formal concept spot-check sample.")
    parser.add_argument("--assignments-path", default=DEFAULT_ASSIGNMENTS_PATH)
    parser.add_argument("--local-to-global-path", default=DEFAULT_LOCAL_TO_GLOBAL_PATH)
    parser.add_argument("--global-summary-path", default=DEFAULT_GLOBAL_SUMMARY_PATH)
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--examples-per-concept", type=int, default=1)
    parser.add_argument("--low-confidence-per-concept", type=int, default=1)
    parser.add_argument("--known-failure-per-concept", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260623)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assignments = pd.read_csv(args.assignments_path).fillna("")
    local_to_global = pd.read_csv(args.local_to_global_path).fillna("")
    global_summary = pd.read_csv(args.global_summary_path).fillna("")

    local_map_cols = [
        "concept_label_llm_suggested",
        "global_concept_label",
        "assignment_confidence",
        "assignment_rationale",
        "final_dimensions",
        "known_failure_links",
    ]
    local_map_cols = [col for col in local_map_cols if col in local_to_global.columns]
    local_map = local_to_global[local_map_cols].drop_duplicates("concept_label_llm_suggested")

    joined = assignments.merge(local_map, on="concept_label_llm_suggested", how="left", suffixes=("_behaviour", "_global"))
    joined = joined.merge(
        global_summary[
            [
                "global_concept_label",
                "review_n",
                "mention_n",
                "candidate_checklist_questions",
                "global_concept_definitions",
            ]
        ],
        on="global_concept_label",
        how="left",
    )

    per_concept = sample_per_group(
        df=joined,
        group_col="global_concept_label",
        n=args.examples_per_concept,
        seed=args.seed,
    )
    per_concept = per_concept.copy()
    per_concept["spotcheck_reason"] = "per_global_concept_sample"

    confidence_col = "assignment_confidence_behaviour"
    if confidence_col not in joined.columns:
        confidence_col = "assignment_confidence"
    low_conf_pool = joined.loc[~joined[confidence_col].astype(str).str.lower().eq("high")].copy()
    low_conf = sample_per_group(
        df=low_conf_pool,
        group_col="global_concept_label",
        n=args.low_confidence_per_concept,
        seed=args.seed,
    )
    low_conf["spotcheck_reason"] = "low_or_medium_behaviour_assignment_confidence"

    known_failure_pool = joined.loc[
        joined["known_failure_links"].astype(str).str.strip().ne("")
        & ~joined["known_failure_links"].astype(str).str.contains("none", case=False, regex=False)
    ].copy()
    known_failure = sample_per_group(
        df=known_failure_pool,
        group_col="global_concept_label",
        n=args.known_failure_per_concept,
        seed=args.seed,
    )
    known_failure["spotcheck_reason"] = "known_failure_linked_concept"

    spotcheck = (
        pd.concat([per_concept, low_conf, known_failure], ignore_index=True)
        .drop_duplicates(["behaviour_id", "global_concept_label", "spotcheck_reason"])
        .sort_values(["spotcheck_reason", "global_concept_label", "review_n"], ascending=[True, True, False])
    )

    preferred_cols = [
        "spotcheck_reason",
        "global_concept_label",
        "global_concept_definitions",
        "candidate_checklist_questions",
        "review_n",
        "mention_n",
        "concept_label_llm_suggested",
        "behaviour_id",
        "dataset",
        "score_tier",
        "dimension_hint",
        "behaviour_type",
        "polarity",
        "behaviour_label",
        "evidence_field",
        "evidence_quote",
        "why_this_is_a_reviewing_behaviour",
        "assignment_confidence_behaviour",
        "assignment_rationale_behaviour",
        "assignment_confidence_global",
        "assignment_rationale_global",
        "known_failure_links",
    ]
    existing_cols = [col for col in preferred_cols if col in spotcheck.columns]
    spotcheck = spotcheck[existing_cols]

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    spotcheck.to_csv(output_path, index=False)

    print(
        {
            "assignments": len(assignments),
            "global_concepts": joined["global_concept_label"].nunique(),
            "spotcheck_rows": len(spotcheck),
            "output_path": str(output_path),
        }
    )


if __name__ == "__main__":
    main()
