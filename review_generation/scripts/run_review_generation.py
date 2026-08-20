"""Run zero-shot review-generation request JSONL and save complete API provenance."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import BadRequestError, OpenAI


DEFAULT_REQUEST_PATH = (
    "outputs/review_generation/requests/"
    "validation_sampling_v0_2_seed20260717_human_pilot_n3_"
    "zero_shot_review_generation_v0_6_pdf_n3_requests.jsonl"
)
DEFAULT_OUTPUT_DIR = "outputs/review_generation/results"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(record: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_model_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as error:
        return None, str(error)
    if not isinstance(parsed, dict):
        return None, "Top-level JSON value is not an object."
    return parsed, None


def is_unsupported_temperature_error(error: BadRequestError) -> bool:
    message = str(error).lower()
    return "unsupported parameter" in message and "temperature" in message


def serialise_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return {"raw": str(usage)}


def build_api_input(request: dict[str, Any]) -> list[dict[str, Any]]:
    """Load the PDF at API-call time to avoid storing base64 in the request JSONL."""

    source = request["source"]
    if source.get("paper_input_mode") != "pdf":
        return request["messages"]

    pdf_path = Path(source["paper_pdf_path"])
    if not pdf_path.is_absolute():
        pdf_path = PROJECT_ROOT / pdf_path
    pdf_bytes = pdf_path.read_bytes()
    actual_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if actual_sha256 != source["paper_pdf_sha256"]:
        raise ValueError(f"PDF hash changed since request build: {pdf_path}")

    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    system_message, user_message = request["messages"]
    return [
        system_message,
        {
            "role": "user",
            "content": [
                {
                    "type": "input_file",
                    "filename": pdf_path.name,
                    "file_data": f"data:application/pdf;base64,{encoded}",
                },
                {"type": "input_text", "text": user_message["content"]},
            ],
        },
    ]


def run_one_request(
    client: OpenAI,
    request: dict[str, Any],
    model: str,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    request_kwargs: dict[str, Any] = {
        "model": model,
        "input": build_api_input(request),
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    temperature_sent = True
    temperature_retry_reason = None
    try:
        response = client.responses.create(**request_kwargs)
    except BadRequestError as error:
        if not is_unsupported_temperature_error(error):
            raise
        temperature_sent = False
        temperature_retry_reason = "model_does_not_support_temperature"
        request_kwargs.pop("temperature", None)
        response = client.responses.create(**request_kwargs)

    raw_text = response.output_text
    parsed_json, parse_error = parse_model_json(raw_text)
    return {
        "request_id": request["request_id"],
        "task": request["task"],
        "prompt_version": request["prompt_version"],
        "model_requested": model,
        "model_returned": getattr(response, "model", None),
        "temperature_requested": temperature,
        "temperature_sent": temperature_sent,
        "temperature_retry_reason": temperature_retry_reason,
        "max_output_tokens": max_output_tokens,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "response_id": getattr(response, "id", None),
        "usage": serialise_usage(response),
        "source": request["source"],
        "raw_output_text": raw_text,
        "parsed_output_json": parsed_json,
        "parse_error": parse_error,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run zero-shot peer-review generation requests."
    )
    parser.add_argument("--request-path", default=DEFAULT_REQUEST_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=5_000)
    parser.add_argument(
        "--limit", type=int, default=0, help="Use 0 to run all requests."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request_path = Path(args.request_path)
    output_dir = Path(args.output_dir)
    requests = read_jsonl(request_path)
    if args.limit > 0:
        requests = requests[: args.limit]

    planned_models = {request.get("model") for request in requests}
    if planned_models != {args.model}:
        raise ValueError(
            f"Request metadata models={sorted(str(model) for model in planned_models)} "
            f"do not match --model={args.model}; rebuild the requests or explicitly "
            "correct the model setting."
        )

    output_path = output_dir / (
        f"{request_path.stem}_results_{args.model}_temp{args.temperature}.jsonl"
    )
    done_ids: set[str] = set()
    if output_path.exists() and not args.no_resume:
        done_ids = {row["request_id"] for row in read_jsonl(output_path)}
    pending = [request for request in requests if request["request_id"] not in done_ids]

    summary: dict[str, Any] = {
        "request_path": str(request_path),
        "output_path": str(output_path),
        "requests_total_selected": len(requests),
        "requests_already_completed": len(requests) - len(pending),
        "requests_to_run": len(pending),
        "model": args.model,
        "temperature_requested": args.temperature,
        "max_output_tokens": args.max_output_tokens,
        "dry_run": args.dry_run,
        "resume": not args.no_resume,
    }
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    client = OpenAI()
    for index, request in enumerate(pending, start=1):
        result = run_one_request(
            client=client,
            request=request,
            model=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
        )
        append_jsonl(result, output_path)
        print(
            json.dumps(
                {
                    "completed_this_run": index,
                    "remaining_this_run": len(pending) - index,
                    "request_id": result["request_id"],
                    "parsed": result["parsed_output_json"] is not None,
                    "parse_error": result["parse_error"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    results = read_jsonl(output_path)
    selected_ids = {request["request_id"] for request in requests}
    selected_results = [row for row in results if row["request_id"] in selected_ids]
    summary["parsed_json_count"] = sum(
        row["parsed_output_json"] is not None for row in selected_results
    )
    summary["parse_error_count"] = len(selected_results) - summary["parsed_json_count"]
    summary["temperature_sent_count"] = sum(
        bool(row["temperature_sent"]) for row in selected_results
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
