"""Run static integrity checks that require neither private data nor API calls."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DIMENSIONS = {
    "Coverage",
    "Substance",
    "Reasoning",
    "Grounding",
    "Constructiveness",
    "Independence",
    "Specificity",
    "Clarity",
    "Ethics",
}
EXPECTED_PROMPT_HEADINGS = {
    "prompts/open_coding.md": "# Open Coding Prompt v0.1",
    "prompts/concept_grouping.md": "# Concept Grouping Prompt v0.1",
    "prompts/concept_consolidation.md": "# Concept Consolidation Prompt v0.1",
    "prompts/review_generation.md": "# Zero-shot peer-review generation prompt v0.6",
    "prompts/checklist_application.md": "# Checklist Application Prompt v0.2",
}
EXPECTED_FILE_HASHES = {
    "prompts/open_coding.md": "fcd1cf8038d8a58698b78dcde3fcdfe726431d0cb643c508ed06f7bb41f3ecb1",
    "prompts/concept_grouping.md": "012301696049551ec1bfd53770e9b77e22a1a709122b9607e0db0d7be2690529",
    "prompts/concept_consolidation.md": "4abcbc1b5625e5e752f96930624cde5349e42e449393aadec20e934adbe73da7",
    "prompts/review_generation.md": "4d14c726304fd70e4cc3c283fbb23e2b2635d63d3d47652b937bac59d917b665",
    "prompts/checklist_application.md": "23d798610844ad77a432bb8f88beb56b1f3f285423b2f20c097b2e869124461d",
    "artifacts/checklist.csv": "60708225a6e1511501a7178edc61ba4414ea0bf237d9c003fab49d74b39a7f9e",
    "artifacts/annotation_guideline.md": "55c7713ca29810af97b559200b83c95753d7fa8d844c8a5c1a220ad464251dde",
}
REQUIRED_DOCUMENTS = [
    ".gitignore",
    ".env.example",
    "README.md",
    "CITATION.cff",
    "requirements.txt",
]
REQUIRED_README_SECTIONS = [
    "## Scope and repository map",
    "## Installation and validation",
    "## Data availability, privacy and third parties",
    "## Reproducing the reported workflow",
    "## Artifact and run provenance",
    "## Citation and licensing status",
]
REQUIRED_SCRIPTS = [
    "scripts/build_checklist.py",
    "scripts/checklist_builder_core.py",
    "scripts/flatten_open_coding_results.py",
    "human_llm_comparison/scripts/analyse_human_llm_ensemble.py",
    "human_llm_comparison/scripts/analyse_ensemble_length_diagnostic.py",
]
IGNORED_TOP_LEVEL = {".git", ".venv", "venv", "data", "inputs", "outputs"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)
        return list(reader.fieldnames or []), list(reader)


def is_ignored(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return bool(relative.parts and relative.parts[0] in IGNORED_TOP_LEVEL)


def check_python_syntax() -> int:
    count = 0
    for path in sorted(ROOT.rglob("*.py")):
        if is_ignored(path):
            continue
        source = path.read_text(encoding="utf-8")
        compile(source, str(path.relative_to(ROOT)), "exec")
        count += 1
    return count


def main() -> None:
    missing = [path for path in REQUIRED_DOCUMENTS if not (ROOT / path).is_file()]
    if missing:
        raise AssertionError(f"Missing release documents: {missing}")
    missing_scripts = [path for path in REQUIRED_SCRIPTS if not (ROOT / path).is_file()]
    if missing_scripts:
        raise AssertionError(f"Missing release scripts: {missing_scripts}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing_sections = [
        section for section in REQUIRED_README_SECTIONS if section not in readme
    ]
    if missing_sections:
        raise AssertionError(f"README sections missing: {missing_sections}")

    prompt_checks = 0
    for relative_path, expected_heading in EXPECTED_PROMPT_HEADINGS.items():
        path = ROOT / relative_path
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        if first_line != expected_heading:
            raise AssertionError(
                f"Unexpected prompt heading in {relative_path}: {first_line!r}"
            )
        prompt_checks += 1

    for relative_path, expected_hash in EXPECTED_FILE_HASHES.items():
        actual_hash = sha256(ROOT / relative_path)
        if actual_hash != expected_hash:
            raise AssertionError(
                f"Unexpected SHA-256 for {relative_path}: {actual_hash}"
            )

    checklist_path = ROOT / "artifacts/checklist.csv"
    if checklist_path.read_bytes().startswith(b"\xef\xbb\xbf"):
        raise AssertionError("artifacts/checklist.csv must be UTF-8 without a BOM")
    checklist_fields, checklist_rows = read_csv(checklist_path)
    expected_fields = [
        "question_id",
        "dimension",
        "candidate_question",
        "answer_scale",
        "needs_paper_text",
    ]
    if checklist_fields != expected_fields:
        raise AssertionError(f"Unexpected checklist fields: {checklist_fields}")
    if len(checklist_rows) != 25:
        raise AssertionError(f"Expected 25 checklist rows, found {len(checklist_rows)}")
    question_ids = [row["question_id"] for row in checklist_rows]
    if len(set(question_ids)) != 25:
        raise AssertionError("Checklist question IDs are not unique")
    dimensions = {row["dimension"] for row in checklist_rows}
    if dimensions != EXPECTED_DIMENSIONS:
        raise AssertionError(f"Unexpected checklist dimensions: {sorted(dimensions)}")
    if {row["answer_scale"] for row in checklist_rows} != {
        "yes/partial/no/not_applicable"
    }:
        raise AssertionError("Unexpected checklist answer scale")

    guideline_hash = sha256(ROOT / "artifacts/annotation_guideline.md")

    cache_directories = [
        path for path in ROOT.rglob("__pycache__") if not is_ignored(path)
    ]
    if cache_directories:
        raise AssertionError(f"Generated Python caches present: {cache_directories}")
    forbidden_extensions = {".jsonl", ".xlsx", ".xls", ".pdf", ".ipynb"}
    forbidden_files = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and not is_ignored(path)
        and path.suffix.lower() in forbidden_extensions
    ]
    if forbidden_files:
        raise AssertionError(f"Restricted/generated file types present: {forbidden_files}")

    forbidden_internal_names = {"AGENTS.md", "CODEX.md", "PROJECT_LOG.md"}
    internal_files = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if not is_ignored(path)
        and (
            path.name in forbidden_internal_names
            or "notes" in {part.lower() for part in path.relative_to(ROOT).parts}
        )
    ]
    if internal_files:
        raise AssertionError(f"Internal project material present: {internal_files}")

    versioned_release_names = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if not is_ignored(path)
        and any(
            part.lower().startswith("v0_")
            or "_v0_" in part.lower()
            or "_v0." in part.lower()
            for part in path.relative_to(ROOT).parts
        )
    ]
    if versioned_release_names:
        raise AssertionError(
            f"Development-version names remain in the public tree: {versioned_release_names}"
        )

    print(
        json.dumps(
            {
                "status": "pass",
                "python_files_syntax_checked": check_python_syntax(),
                "prompts_checked": prompt_checks,
                "checklist_items": len(checklist_rows),
                "checklist_dimensions": len(dimensions),
                "annotation_guideline_sha256": guideline_hash,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
