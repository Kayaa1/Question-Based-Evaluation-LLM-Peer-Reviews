"""Build request JSONL files for automated checklist application.

This script is the entry point for the automation pipeline. It combines sampled
reviews, the current checklist, the annotation guideline, and paper context into
requests that can be submitted to an LLM.

This is a non-diagnostic application pipeline: the model applies the existing
checklist labels (yes/partial/no/not_applicable) and produces a structured profile.
It does not revise the guideline or identify checklist items that are difficult to
distinguish.

Three paper-context modes are supported:
- itg_truncated: include text from paper.itg.json directly and truncate it at the
  configured limit.
- rag_bm25: query paper.itg.json chunks with the review, title, and abstract, then
  select relevant excerpts. This is lightweight context selection, not final
  claim-level RAG.
- openai_embedding: use OpenAI embeddings for semantic retrieval without FAISS.
  This mode is a small ablation that tests whether it retrieves more useful chunks
  than BM25.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from string import Template
from typing import Any

from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE_PATH = (
    "outputs/sampling/"
    "nlpeer_review_sample_ARR22-ARREMNLP24v1.1-EMNLP23_n180_seed20260613.csv"
)
DEFAULT_CHECKLIST_PATH = "artifacts/checklist.csv"
DEFAULT_GUIDELINE_PATH = "artifacts/annotation_guideline.md"
DEFAULT_PROMPT_PATH = "prompts/checklist_application.md"
DEFAULT_OUTPUT_DIR = "outputs/checklist_application/requests"
DEFAULT_DATA_ROOT = "data"
DEFAULT_EMBEDDING_CACHE_PATH = (
    "outputs/checklist_application/embedding_cache/openai_embeddings_cache.jsonl"
)
DEFAULT_MAX_EMBEDDING_INPUT_CHARS = 12000

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "paper",
    "review",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
}

BALANCED_TARGETS = [
    ("ARR-22", "high"),
    ("ARR-22", "mid"),
    ("ARR-22", "low"),
    ("ARR-EMNLP-24-v1.1", "high"),
    ("ARR-EMNLP-24-v1.1", "mid"),
    ("ARR-EMNLP-24-v1.1", "low"),
    ("EMNLP23", "high"),
    ("EMNLP23", "mid"),
    ("EMNLP23", "low"),
]


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def display_path(path: Path) -> str:
    """Prefer a repository-relative path; keep external test paths absolute."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def make_review_record_id(row: dict[str, str]) -> str:
    if row.get("review_record_id"):
        return row["review_record_id"]
    return "::".join([row["dataset"], row["paper_id"], row["version"], row["review_index"]])


def truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[TRUNCATED]"


def find_paper_itg_path(row: dict[str, str], data_root: Path) -> Path | None:
    """Locate paper.itg.json for the review's paper and version.

    NLPeer reviews normally reside inside a version directory. Prefer paper text
    from that version; if it has no paper.itg.json, fall back to the first available
    version for the paper. This choice affects paper-aware judgements, so the path
    is recorded in request metadata for later inspection.
    """
    if row.get("paper_itg_path"):
        direct_path = Path(row["paper_itg_path"])
        direct_path = direct_path if direct_path.is_absolute() else PROJECT_ROOT / direct_path
        if direct_path.exists():
            return direct_path

    reviews_path = data_root / row["source_reviews_path"]
    version_dir = reviews_path.parent
    same_version_path = version_dir / "paper.itg.json"
    if same_version_path.exists():
        return same_version_path

    paper_dir = version_dir.parent
    candidates = sorted(paper_dir.glob("v*/paper.itg.json"))
    return candidates[0] if candidates else None


def format_itg_node(node: dict[str, Any]) -> str:
    """Convert an NLPeer ITG node into a linear text block for the model."""
    content = " ".join(str(node.get("content", "")).split())
    if not content:
        return ""

    ntype = str(node.get("ntype", "text"))
    if ntype == "heading":
        section = ""
        meta = node.get("meta")
        if isinstance(meta, dict) and meta.get("section"):
            section = f" {meta['section']}"
        return f"\n## Section{section}: {content}\n"
    if ntype in {"title", "abstract"}:
        return f"\n[{ntype.upper()}] {content}\n"
    return content


def tokenize(text: str) -> list[str]:
    """Tokenize text for lightweight BM25 context selection.

    This avoids additional NLP dependencies so the RAG pilot remains reproducible,
    readable, and easy to tune. It supports only coarse-grained chunk retrieval,
    not formal semantic parsing.
    """
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_'-]+|\d+(?:\.\d+)?", text.lower())
    return [token for token in tokens if token not in STOPWORDS and len(token) > 1]


def split_long_text(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    words = text.split()
    current: list[str] = []
    current_len = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and current_len + extra > max_chars:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += extra
    if current:
        chunks.append(" ".join(current))
    return chunks


def section_label(node: dict[str, Any], current_section: str) -> str:
    meta = node.get("meta")
    if isinstance(meta, dict) and meta.get("section"):
        return str(meta["section"])
    return current_section


def build_paper_chunks(
    paper: dict[str, Any], max_chunk_chars: int
) -> tuple[list[dict[str, Any]], str]:
    """Build BM25 chunks from paper.itg.json and retain a full-text baseline.

    Each chunk retains metadata such as node type, section, and node index so the
    paper excerpts supplied by RAG-BM25 can be inspected later.
    """
    chunks: list[dict[str, Any]] = []
    current_section = ""
    full_pieces: list[str] = []

    for node_index, node in enumerate(paper.get("nodes", [])):
        content = " ".join(str(node.get("content", "")).split())
        if not content:
            continue

        ntype = str(node.get("ntype", "text"))
        if ntype == "heading":
            current_section = section_label(node, current_section)

        formatted = format_itg_node(node)
        if formatted:
            full_pieces.append(formatted)

        section = section_label(node, current_section)
        for part_index, text_part in enumerate(split_long_text(content, max_chunk_chars)):
            chunk_id = f"node{node_index:04d}_part{part_index:02d}"
            prefix_parts = [f"[CHUNK {chunk_id}]", f"[TYPE {ntype}]"]
            if section:
                prefix_parts.append(f"[SECTION {section}]")
            chunk_text = " ".join(prefix_parts) + f"\n{text_part}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "node_index": node_index,
                    "part_index": part_index,
                    "ntype": ntype,
                    "section": section,
                    "text": chunk_text,
                    "raw_text": text_part,
                    "tokens": tokenize(text_part),
                }
            )

    return chunks, "\n".join(full_pieces)


def bm25_scores(query: str, chunks: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    """Calculate BM25 scores between a query and paper chunks.

    The query combines the paper title, abstract, and review text so retrieval
    prioritises paper content that the reviewer actually discusses.
    """
    query_tokens = tokenize(query)
    if not query_tokens or not chunks:
        return []

    doc_tokens = [chunk["tokens"] for chunk in chunks]
    doc_lens = [len(tokens) for tokens in doc_tokens]
    avgdl = sum(doc_lens) / len(doc_lens) if doc_lens else 0.0
    if avgdl <= 0:
        return []

    dfs: Counter[str] = Counter()
    for tokens in doc_tokens:
        dfs.update(set(tokens))

    query_counts = Counter(query_tokens)
    n_docs = len(chunks)
    k1 = 1.5
    b = 0.75
    scored: list[tuple[float, dict[str, Any]]] = []

    for chunk, tokens, doc_len in zip(chunks, doc_tokens, doc_lens, strict=True):
        term_counts = Counter(tokens)
        score = 0.0
        for token, query_tf in query_counts.items():
            tf = term_counts.get(token, 0)
            if tf == 0:
                continue
            df = dfs[token]
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1 - b + b * doc_len / avgdl)
            score += query_tf * idf * (tf * (k1 + 1) / denom)
        if score > 0:
            scored.append((score, chunk))

    return sorted(scored, key=lambda item: item[0], reverse=True)


def embedding_cache_key(model: str, text: str) -> str:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{model}:{text_hash}"


def truncate_embedding_text(text: str, max_chars: int) -> str:
    """Limit each embedding input to avoid exceeding the endpoint token limit."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n[EMBEDDING_INPUT_TRUNCATED]"


def load_embedding_cache(path: Path) -> dict[str, list[float]]:
    """Load the OpenAI embedding cache.

    The cache resides under ignored outputs and stores only text hashes, not source
    text, to avoid duplicating paper or review content. Rebuilding the same request
    batch therefore does not require repeated embedding API calls.
    """
    if not path.exists():
        return {}

    cache: dict[str, list[float]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            cache[record["key"]] = record["embedding"]
    return cache


def append_embedding_cache(
    path: Path,
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_openai_embeddings(
    texts: list[str],
    model: str,
    cache_path: Path,
    batch_size: int,
    max_input_chars: int,
) -> list[list[float]]:
    """Obtain text vectors from the OpenAI embeddings API.

    This is a retrieval-only ablation: only query and chunk text is sent to the
    embeddings endpoint. Returned vectors are used for local cosine similarity,
    without FAISS or an external vector database.
    """
    embedding_texts = [
        truncate_embedding_text(text, max_input_chars) for text in texts
    ]
    cache = load_embedding_cache(cache_path)
    keys = [embedding_cache_key(model, text) for text in embedding_texts]
    missing_indices = [index for index, key in enumerate(keys) if key not in cache]

    if missing_indices:
        client = OpenAI()
        new_cache_records: list[dict[str, Any]] = []
        for start in range(0, len(missing_indices), batch_size):
            batch_indices = missing_indices[start : start + batch_size]
            batch_texts = [embedding_texts[index] for index in batch_indices]
            response = client.embeddings.create(
                model=model,
                input=batch_texts,
                encoding_format="float",
            )
            for item in sorted(response.data, key=lambda data: data.index):
                source_index = batch_indices[item.index]
                key = keys[source_index]
                cache[key] = item.embedding
                new_cache_records.append(
                    {
                        "key": key,
                        "model": model,
                        "embedding": item.embedding,
                    }
                )
        append_embedding_cache(cache_path, new_cache_records)

    return [cache[key] for key in keys]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def embedding_scores(
    query: str,
    chunks: list[dict[str, Any]],
    model: str,
    cache_path: Path,
    batch_size: int,
    max_input_chars: int,
) -> list[tuple[float, dict[str, Any]]]:
    """Rank chunks using OpenAI embeddings and cosine similarity."""
    if not query.strip() or not chunks:
        return []

    texts = [query] + [chunk["raw_text"] for chunk in chunks]
    embeddings = get_openai_embeddings(
        texts=texts,
        model=model,
        cache_path=cache_path,
        batch_size=batch_size,
        max_input_chars=max_input_chars,
    )
    query_embedding = embeddings[0]
    scored = [
        (cosine_similarity(query_embedding, chunk_embedding), chunk)
        for chunk, chunk_embedding in zip(chunks, embeddings[1:], strict=True)
    ]
    return sorted(scored, key=lambda item: item[0], reverse=True)


def build_rag_context(
    paper: dict[str, Any],
    row: dict[str, str],
    top_k: int,
    max_chunk_chars: int,
    max_paper_chars: int,
) -> dict[str, Any]:
    """Build the paper context supplied to the model in rag_bm25 mode.

    The title and abstract are always retained because they establish the paper's
    task and contributions. The remaining top-k chunks are selected by BM25 score.
    The result includes both context text and retrieval metadata for comparing RAG
    with the near-full ITG context.
    """
    chunks, full_context = build_paper_chunks(paper, max_chunk_chars)
    query = "\n".join([row.get("title", ""), row.get("abstract", ""), row.get("review_text", "")])

    always_chunks = [
        chunk for chunk in chunks if chunk["ntype"] in {"title", "abstract"}
    ]
    always_ids = {chunk["chunk_id"] for chunk in always_chunks}
    candidate_chunks = [chunk for chunk in chunks if chunk["chunk_id"] not in always_ids]
    ranked = bm25_scores(query, candidate_chunks)

    if ranked:
        retrieved = [chunk for _, chunk in ranked[:top_k]]
        score_by_id = {chunk["chunk_id"]: score for score, chunk in ranked}
    else:
        retrieved = candidate_chunks[:top_k]
        score_by_id = {chunk["chunk_id"]: 0.0 for chunk in retrieved}

    selected = always_chunks + retrieved
    selected_ids = set()
    unique_selected = []
    for chunk in selected:
        if chunk["chunk_id"] not in selected_ids:
            unique_selected.append(chunk)
            selected_ids.add(chunk["chunk_id"])

    parts = [
        "Retrieved paper context selected with lightweight BM25 over paper.itg.json chunks.",
        f"Full paper chars before retrieval: {len(full_context)}.",
        f"Selected chunks: {len(unique_selected)} (title/abstract always included when available; top_k={top_k}).",
        "",
    ]
    for rank, chunk in enumerate(unique_selected, start=1):
        score = score_by_id.get(chunk["chunk_id"], 0.0)
        parts.append(
            f"[RANK {rank}] [BM25_SCORE {score:.3f}] "
            f"[CHUNK_ID {chunk['chunk_id']}] [TYPE {chunk['ntype']}]"
        )
        if chunk.get("section"):
            parts.append(f"[SECTION {chunk['section']}]")
        parts.append(chunk["raw_text"])
        parts.append("")

    paper_context = "\n".join(parts)
    truncated = max_paper_chars > 0 and len(paper_context) > max_paper_chars
    paper_context = truncate_text(paper_context, max_paper_chars)

    return {
        "paper_context": paper_context,
        "paper_context_chars": len(paper_context),
        "paper_context_truncated": truncated,
        "paper_context_full_chars": len(full_context),
        "paper_context_selected_chunk_n": len(unique_selected),
        "paper_context_total_chunk_n": len(chunks),
        "paper_context_retrieval_query_chars": len(query),
        "paper_context_retrieval_model": "bm25",
    }


def build_openai_embedding_context(
    paper: dict[str, Any],
    row: dict[str, str],
    top_k: int,
    max_chunk_chars: int,
    max_paper_chars: int,
    embedding_model: str,
    embedding_cache_path: Path,
    embedding_batch_size: int,
    max_embedding_input_chars: int,
) -> dict[str, Any]:
    """Build the paper context supplied to the model in openai_embedding mode.

    The retrieval query remains the title, abstract, and full review, providing a
    fair comparison with BM25. Only the ranking signal changes, from keyword
    overlap to semantic vector similarity.
    """
    chunks, full_context = build_paper_chunks(paper, max_chunk_chars)
    query = "\n".join([row.get("title", ""), row.get("abstract", ""), row.get("review_text", "")])

    always_chunks = [
        chunk for chunk in chunks if chunk["ntype"] in {"title", "abstract"}
    ]
    always_ids = {chunk["chunk_id"] for chunk in always_chunks}
    candidate_chunks = [chunk for chunk in chunks if chunk["chunk_id"] not in always_ids]
    ranked = embedding_scores(
        query=query,
        chunks=candidate_chunks,
        model=embedding_model,
        cache_path=embedding_cache_path,
        batch_size=embedding_batch_size,
        max_input_chars=max_embedding_input_chars,
    )

    if ranked:
        retrieved = [chunk for _, chunk in ranked[:top_k]]
        score_by_id = {chunk["chunk_id"]: score for score, chunk in ranked}
    else:
        retrieved = candidate_chunks[:top_k]
        score_by_id = {chunk["chunk_id"]: 0.0 for chunk in retrieved}

    selected = always_chunks + retrieved
    selected_ids = set()
    unique_selected = []
    for chunk in selected:
        if chunk["chunk_id"] not in selected_ids:
            unique_selected.append(chunk)
            selected_ids.add(chunk["chunk_id"])

    parts = [
        "Retrieved paper context selected with OpenAI embeddings over paper.itg.json chunks.",
        f"Embedding model: {embedding_model}.",
        f"Full paper chars before retrieval: {len(full_context)}.",
        f"Selected chunks: {len(unique_selected)} (title/abstract always included when available; top_k={top_k}).",
        "",
    ]
    for rank, chunk in enumerate(unique_selected, start=1):
        score = score_by_id.get(chunk["chunk_id"], 0.0)
        parts.append(
            f"[RANK {rank}] [EMBED_SCORE {score:.3f}] "
            f"[CHUNK_ID {chunk['chunk_id']}] [TYPE {chunk['ntype']}]"
        )
        if chunk.get("section"):
            parts.append(f"[SECTION {chunk['section']}]")
        parts.append(chunk["raw_text"])
        parts.append("")

    paper_context = "\n".join(parts)
    truncated = max_paper_chars > 0 and len(paper_context) > max_paper_chars
    paper_context = truncate_text(paper_context, max_paper_chars)

    return {
        "paper_context": paper_context,
        "paper_context_chars": len(paper_context),
        "paper_context_truncated": truncated,
        "paper_context_full_chars": len(full_context),
        "paper_context_selected_chunk_n": len(unique_selected),
        "paper_context_total_chunk_n": len(chunks),
        "paper_context_retrieval_query_chars": len(query),
        "paper_context_retrieval_model": embedding_model,
        "openai_embedding_max_input_chars": max_embedding_input_chars,
    }


def read_paper_context(
    row: dict[str, str],
    data_root: Path,
    max_paper_chars: int,
    paper_context_mode: str,
    rag_top_k: int,
    rag_max_chunk_chars: int,
    openai_embedding_model: str,
    embedding_cache_path: Path,
    embedding_batch_size: int,
    max_embedding_input_chars: int,
) -> dict[str, Any]:
    """Read and format paper context.

    This function handles all three context modes and records metadata such as
    characters sent, full-text characters, and chunk counts. When answer changes
    are analysed later, these fields help determine whether context compression or
    retrieval selection may have caused them.
    """
    paper_path = find_paper_itg_path(row, data_root)
    if paper_path is None:
        return {
            "paper_context": "[PAPER CONTEXT NOT FOUND]",
            "paper_context_path": "",
            "paper_context_chars": 0,
            "paper_context_truncated": False,
            "paper_context_full_chars": 0,
            "paper_context_selected_chunk_n": 0,
            "paper_context_total_chunk_n": 0,
            "paper_context_retrieval_query_chars": 0,
            "paper_context_retrieval_model": "",
            "openai_embedding_max_input_chars": "",
        }

    with paper_path.open(encoding="utf-8") as f:
        paper = json.load(f)

    if paper_context_mode == "rag_bm25":
        context_info = build_rag_context(
            paper=paper,
            row=row,
            top_k=rag_top_k,
            max_chunk_chars=rag_max_chunk_chars,
            max_paper_chars=max_paper_chars,
        )
        return {
            **context_info,
            "paper_context_path": str(paper_path.relative_to(PROJECT_ROOT)),
        }

    if paper_context_mode == "openai_embedding":
        context_info = build_openai_embedding_context(
            paper=paper,
            row=row,
            top_k=rag_top_k,
            max_chunk_chars=rag_max_chunk_chars,
            max_paper_chars=max_paper_chars,
            embedding_model=openai_embedding_model,
            embedding_cache_path=embedding_cache_path,
            embedding_batch_size=embedding_batch_size,
            max_embedding_input_chars=max_embedding_input_chars,
        )
        return {
            **context_info,
            "paper_context_path": str(paper_path.relative_to(PROJECT_ROOT)),
        }

    pieces = []
    for node in paper.get("nodes", []):
        text = format_itg_node(node)
        if text:
            pieces.append(text)

    paper_context = "\n".join(pieces)
    full_chars = len(paper_context)
    truncated = max_paper_chars > 0 and len(paper_context) > max_paper_chars
    paper_context = truncate_text(paper_context, max_paper_chars)

    return {
        "paper_context": paper_context,
        "paper_context_path": str(paper_path.relative_to(PROJECT_ROOT)),
        "paper_context_chars": len(paper_context),
        "paper_context_truncated": truncated,
        "paper_context_full_chars": full_chars,
        "paper_context_selected_chunk_n": 0,
        "paper_context_total_chunk_n": 0,
        "paper_context_retrieval_query_chars": 0,
        "paper_context_retrieval_model": "",
        "openai_embedding_max_input_chars": "",
    }


def infer_guideline_version(guideline_path: Path) -> str:
    return guideline_path.stem


def infer_checklist_version(checklist_path: Path) -> str:
    stem = checklist_path.stem
    if "checklist_draft_v0_3" in stem:
        return "checklist_draft_v0_3"
    return stem


def choose_rows(
    rows: list[dict[str, str]],
    limit: int,
    selection: str,
) -> list[dict[str, str]]:
    """Select sampled reviews for which requests will be built.

    Balanced mode first selects nine seed rows spanning three datasets and three
    score tiers for a small-scale sanity check. First mode takes only the first N
    CSV rows, which is useful for reproducing a run or debugging a fixed input
    order.
    """
    if selection == "first":
        return rows if limit <= 0 else rows[:limit]

    selected: list[dict[str, str]] = []
    for dataset, tier in BALANCED_TARGETS:
        match = next(
            row for row in rows if row["dataset"] == dataset and row["score_tier"] == tier
        )
        selected.append(match)

    if limit <= 0:
        return rows
    if limit <= len(selected):
        return selected[:limit]

    selected_ids = {make_review_record_id(row) for row in selected}
    for row in rows:
        if len(selected) >= limit:
            break
        if make_review_record_id(row) not in selected_ids:
            selected.append(row)
    return selected


def format_checklist(checklist_rows: list[dict[str, str]]) -> str:
    """Format the checklist CSV as a stable, readable prompt item block."""
    lines = []
    for row in checklist_rows:
        lines.append(
            "\n".join(
                [
                    f"- question_id: {row['question_id']}",
                    f"  dimension: {row['dimension']}",
                    f"  needs_paper_text: {row['needs_paper_text']}",
                    f"  answer_scale: {row['answer_scale']}",
                    f"  question: {row['candidate_question']}",
                ]
            )
        )
    return "\n".join(lines)


def build_user_input(
    row: dict[str, str],
    checklist_text: str,
    guideline_text: str,
    max_review_chars: int,
    paper_context_info: dict[str, Any],
) -> str:
    """Combine a review and supporting material into a source-blind message."""
    review_record_id = make_review_record_id(row)
    review_text = truncate_text(row["review_text"], max_review_chars)

    template = Template(
        """Review metadata:
- review_record_id: $review_record_id
- dataset: $dataset
- paper_id: $paper_id
- version: $version
- paper_title: $title
- venue_or_cycle: $venue_or_cycle
- report_fields: $report_fields
- paper_context_mode: $paper_context_mode
- paper_context_path: $paper_context_path
- paper_context_chars_sent: $paper_context_chars
- paper_context_truncated: $paper_context_truncated
- paper_context_full_chars: $paper_context_full_chars
- paper_context_selected_chunk_n: $paper_context_selected_chunk_n
- paper_context_total_chunk_n: $paper_context_total_chunk_n
- paper_context_retrieval_model: $paper_context_retrieval_model

Checklist items to answer:
$checklist_text

Annotation guideline:
$guideline_text

Paper context:
$paper_context

Peer review text:
$review_text
"""
    )

    return template.substitute(
        review_record_id=review_record_id,
        dataset=row["dataset"],
        paper_id=row["paper_id"],
        version=row["version"],
        title=row["title"],
        venue_or_cycle=row["venue_or_cycle"],
        report_fields=row["report_fields"],
        paper_context_mode=paper_context_info["paper_context_mode"],
        paper_context_path=paper_context_info["paper_context_path"],
        paper_context_chars=paper_context_info["paper_context_chars"],
        paper_context_truncated=paper_context_info["paper_context_truncated"],
        paper_context_full_chars=paper_context_info["paper_context_full_chars"],
        paper_context_selected_chunk_n=paper_context_info["paper_context_selected_chunk_n"],
        paper_context_total_chunk_n=paper_context_info["paper_context_total_chunk_n"],
        paper_context_retrieval_model=paper_context_info["paper_context_retrieval_model"],
        checklist_text=checklist_text,
        guideline_text=guideline_text,
        paper_context=paper_context_info["paper_context"],
        review_text=review_text,
    )


def build_request(
    row: dict[str, str],
    prompt_text: str,
    checklist_text: str,
    guideline_text: str,
    prompt_version: str,
    model: str,
    max_review_chars: int,
    data_root: Path,
    max_paper_chars: int,
    paper_context_mode: str,
    rag_top_k: int,
    rag_max_chunk_chars: int,
    checklist_version: str,
    guideline_version: str,
    openai_embedding_model: str,
    embedding_cache_path: Path,
    embedding_batch_size: int,
    max_embedding_input_chars: int,
) -> dict[str, Any]:
    """Build one API request and record key versions and context metadata."""
    review_record_id = make_review_record_id(row)
    paper_context_info = read_paper_context(
        row=row,
        data_root=data_root,
        max_paper_chars=max_paper_chars,
        paper_context_mode=paper_context_mode,
        rag_top_k=rag_top_k,
        rag_max_chunk_chars=rag_max_chunk_chars,
        openai_embedding_model=openai_embedding_model,
        embedding_cache_path=embedding_cache_path,
        embedding_batch_size=embedding_batch_size,
        max_embedding_input_chars=max_embedding_input_chars,
    )
    paper_context_info["paper_context_mode"] = paper_context_mode

    return {
        "request_id": (
            f"checklist_application::{prompt_version}::{paper_context_mode}::"
            f"{review_record_id}"
        ),
        "task": "checklist_application",
        "prompt_version": prompt_version,
        "model": model,
        "source": {
            "review_record_id": review_record_id,
            "pair_id": row.get("pair_id", ""),
            "source_type": row.get("source_type", ""),
            "dataset": row["dataset"],
            "paper_id": row["paper_id"],
            "paper_title": row["title"],
            "version": row["version"],
            "review_index": row["review_index"],
            "score_tier_for_sampling_only": row["score_tier"],
            "score_proxy_field_for_sampling_only": row["score_proxy_field"],
            "score_proxy_raw_for_sampling_only": row["score_proxy_raw"],
            "checklist_version": checklist_version,
            "guideline_version": guideline_version,
            "paper_context_mode": paper_context_mode,
            "paper_context_path": paper_context_info["paper_context_path"],
            "paper_context_chars_sent": paper_context_info["paper_context_chars"],
            "paper_context_truncated": paper_context_info["paper_context_truncated"],
            "paper_context_full_chars": paper_context_info["paper_context_full_chars"],
            "paper_context_selected_chunk_n": paper_context_info[
                "paper_context_selected_chunk_n"
            ],
            "paper_context_total_chunk_n": paper_context_info[
                "paper_context_total_chunk_n"
            ],
            "paper_context_retrieval_query_chars": paper_context_info[
                "paper_context_retrieval_query_chars"
            ],
            "paper_context_retrieval_model": paper_context_info[
                "paper_context_retrieval_model"
            ],
            "rag_top_k": (
                rag_top_k if paper_context_mode in {"rag_bm25", "openai_embedding"} else ""
            ),
            "rag_max_chunk_chars": (
                rag_max_chunk_chars
                if paper_context_mode in {"rag_bm25", "openai_embedding"}
                else ""
            ),
            "openai_embedding_model": (
                openai_embedding_model if paper_context_mode == "openai_embedding" else ""
            ),
            "openai_embedding_max_input_chars": (
                max_embedding_input_chars
                if paper_context_mode == "openai_embedding"
                else ""
            ),
        },
        "messages": [
            {"role": "system", "content": prompt_text},
            {
                "role": "user",
                "content": build_user_input(
                    row=row,
                    checklist_text=checklist_text,
                    guideline_text=guideline_text,
                    max_review_chars=max_review_chars,
                    paper_context_info=paper_context_info,
                ),
            },
        ],
        "expected_output": "valid_json_only",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build automated checklist-application request JSONL."
    )
    parser.add_argument("--sample-path", default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--checklist-path", default=DEFAULT_CHECKLIST_PATH)
    parser.add_argument("--guideline-path", default=DEFAULT_GUIDELINE_PATH)
    parser.add_argument("--prompt-path", default=DEFAULT_PROMPT_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--output-stem",
        default="",
        help="Optional filename stem; useful for formal comparison runs.",
    )
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--prompt-version", default="checklist_application_v0_2")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument(
        "--limit",
        type=int,
        default=9,
        help="Number of requests to emit. Use 0 for all sample rows.",
    )
    parser.add_argument(
        "--selection",
        choices=["balanced", "first"],
        default="balanced",
        help="Use balanced dataset/tier seed rows or the first rows from the sample.",
    )
    parser.add_argument("--max-review-chars", type=int, default=12000)
    parser.add_argument("--max-paper-chars", type=int, default=50000)
    parser.add_argument(
        "--paper-context-mode",
        choices=["itg_truncated", "rag_bm25", "openai_embedding"],
        default="itg_truncated",
        help="How to provide paper context to the model.",
    )
    parser.add_argument(
        "--rag-top-k",
        type=int,
        default=18,
        help="Number of chunks to retrieve in rag_bm25 or openai_embedding mode.",
    )
    parser.add_argument(
        "--rag-max-chunk-chars",
        type=int,
        default=1200,
        help="Maximum characters per paper chunk before retrieval.",
    )
    parser.add_argument(
        "--openai-embedding-model",
        default="text-embedding-3-small",
        help="OpenAI embedding model used when --paper-context-mode openai_embedding.",
    )
    parser.add_argument(
        "--embedding-cache-path",
        default=DEFAULT_EMBEDDING_CACHE_PATH,
        help="JSONL cache for OpenAI embeddings; stores text hashes and vectors, not raw text.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=128,
        help="Batch size for OpenAI embedding requests.",
    )
    parser.add_argument(
        "--max-embedding-input-chars",
        type=int,
        default=DEFAULT_MAX_EMBEDDING_INPUT_CHARS,
        help="Safety cap for each text sent to the OpenAI embeddings endpoint.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sample_path = resolve_path(args.sample_path)
    checklist_path = resolve_path(args.checklist_path)
    guideline_path = resolve_path(args.guideline_path)
    prompt_path = resolve_path(args.prompt_path)
    output_dir = resolve_path(args.output_dir)
    data_root = resolve_path(args.data_root)
    embedding_cache_path = resolve_path(args.embedding_cache_path)

    sample_rows = read_csv_rows(sample_path)
    checklist_rows = read_csv_rows(checklist_path)
    selected_rows = choose_rows(sample_rows, args.limit, args.selection)
    checklist_text = format_checklist(checklist_rows)
    guideline_text = read_text(guideline_path)
    prompt_text = read_text(prompt_path)
    checklist_version = infer_checklist_version(checklist_path)
    guideline_version = infer_guideline_version(guideline_path)

    requests = [
        build_request(
            row=row,
            prompt_text=prompt_text,
            checklist_text=checklist_text,
            guideline_text=guideline_text,
            prompt_version=args.prompt_version,
            model=args.model,
            max_review_chars=args.max_review_chars,
            data_root=data_root,
            max_paper_chars=args.max_paper_chars,
            paper_context_mode=args.paper_context_mode,
            rag_top_k=args.rag_top_k,
            rag_max_chunk_chars=args.rag_max_chunk_chars,
            checklist_version=checklist_version,
            guideline_version=guideline_version,
            openai_embedding_model=args.openai_embedding_model,
            embedding_cache_path=embedding_cache_path,
            embedding_batch_size=args.embedding_batch_size,
            max_embedding_input_chars=args.max_embedding_input_chars,
        )
        for row in selected_rows
    ]

    output_slug = args.prompt_version
    if args.paper_context_mode != "itg_truncated":
        output_slug = f"{output_slug}_{args.paper_context_mode}"
    if args.output_stem:
        output_slug = args.output_stem
    output_path = output_dir / f"{output_slug}_n{len(requests)}_requests.jsonl"
    write_jsonl(requests, output_path)

    print(
        json.dumps(
            {
                "sample_path": display_path(sample_path),
                "checklist_path": display_path(checklist_path),
                "guideline_path": display_path(guideline_path),
                "prompt_path": display_path(prompt_path),
                "output_path": display_path(output_path),
                "requests": len(requests),
                "selection": args.selection,
                "checklist_version": checklist_version,
                "guideline_version": guideline_version,
                "paper_context_mode": args.paper_context_mode,
                "rag_top_k": (
                    args.rag_top_k
                    if args.paper_context_mode in {"rag_bm25", "openai_embedding"}
                    else ""
                ),
                "rag_max_chunk_chars": (
                    args.rag_max_chunk_chars
                    if args.paper_context_mode in {"rag_bm25", "openai_embedding"}
                    else ""
                ),
                "openai_embedding_model": (
                    args.openai_embedding_model
                    if args.paper_context_mode == "openai_embedding"
                    else ""
                ),
                "max_embedding_input_chars": (
                    args.max_embedding_input_chars
                    if args.paper_context_mode == "openai_embedding"
                    else ""
                ),
                "embedding_cache_path": (
                    display_path(embedding_cache_path)
                    if args.paper_context_mode == "openai_embedding"
                    else ""
                ),
                "selected": [
                    {
                        "review_record_id": make_review_record_id(row),
                        "dataset": row["dataset"],
                        "score_tier": row["score_tier"],
                        "review_word_count": row["review_word_count"],
                        "paper_context_mode": request["source"]["paper_context_mode"],
                        "paper_context_path": request["source"]["paper_context_path"],
                        "paper_context_chars_sent": request["source"][
                            "paper_context_chars_sent"
                        ],
                        "paper_context_truncated": request["source"][
                            "paper_context_truncated"
                        ],
                        "paper_context_full_chars": request["source"][
                            "paper_context_full_chars"
                        ],
                        "paper_context_selected_chunk_n": request["source"][
                            "paper_context_selected_chunk_n"
                        ],
                        "paper_context_retrieval_model": request["source"][
                            "paper_context_retrieval_model"
                        ],
                    }
                    for row, request in zip(selected_rows, requests, strict=True)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
