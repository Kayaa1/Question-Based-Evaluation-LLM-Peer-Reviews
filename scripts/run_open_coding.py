"""Run JSONL requests for LLM-assisted open coding.

By default, only the first three requests are run, which is suitable for a
pilot. Set ``--limit 0`` to run the complete request file. The script appends
each result to the ignored ``outputs/open_coding/results/`` directory and, by
default, skips ``request_id`` values already completed in the same output file
so an interrupted run can resume.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openai import BadRequestError, OpenAI


DEFAULT_REQUEST_PATH = (
    "outputs/open_coding/requests/"
    "nlpeer_review_sample_ARR22-ARREMNLP24v1.1-EMNLP23_n180_seed20260613_"
    "open_coding_v0_1_n5_requests.jsonl"
)
DEFAULT_OUTPUT_DIR = "outputs/open_coding/results"


def is_unsupported_temperature_error(error: BadRequestError) -> bool:
    """Check whether an API error only indicates unsupported temperature."""

    message = str(error).lower()
    return "unsupported parameter" in message and "temperature" in message


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_model_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse model-returned JSON, preserving the error and raw text on failure."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError as error:
        return None, str(error)


def serialise_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return {"raw": str(usage)}


def checklist_application_json_schema() -> dict[str, Any]:
    """JSON schema used for Claude native Structured Outputs."""

    answer_schema = {
        "type": "object",
        "properties": {
            "question_id": {"type": "string"},
            "dimension": {
                "type": "string",
                "enum": [
                    "Coverage",
                    "Substance",
                    "Reasoning",
                    "Grounding",
                    "Constructiveness",
                    "Independence",
                    "Specificity",
                    "Clarity",
                    "Ethics",
                ],
            },
            "answer": {
                "type": "string",
                "enum": ["yes", "partial", "no", "not_applicable"],
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "review_evidence_quote": {"type": "string"},
            "review_evidence_field": {"type": "string"},
            "paper_evidence_quote": {"type": "string"},
            "paper_evidence_chunk_id": {"type": "string"},
            "paper_evidence_section": {"type": "string"},
            "paper_evidence_status": {
                "type": "string",
                "enum": [
                    "used",
                    "not_needed",
                    "not_found",
                    "paper_context_missing",
                    "not_applicable",
                ],
            },
            "evidence_note": {"type": "string"},
            "paper_evidence_note": {"type": "string"},
            "rationale": {"type": "string"},
            "context_limitation": {
                "type": "string",
                "enum": ["none", "paper_context_truncated", "paper_context_missing", "other"],
            },
        },
        "required": [
            "question_id",
            "dimension",
            "answer",
            "confidence",
            "review_evidence_quote",
            "review_evidence_field",
            "paper_evidence_quote",
            "paper_evidence_chunk_id",
            "paper_evidence_section",
            "paper_evidence_status",
            "evidence_note",
            "paper_evidence_note",
            "rationale",
            "context_limitation",
        ],
        "additionalProperties": False,
    }
    dimension_summary_schema = {
        "type": "object",
        "properties": {
            "dimension": {"type": "string"},
            "yes_n": {"type": "integer"},
            "partial_n": {"type": "integer"},
            "no_n": {"type": "integer"},
            "not_applicable_n": {"type": "integer"},
            "profile": {"type": "string"},
        },
        "required": [
            "dimension",
            "yes_n",
            "partial_n",
            "no_n",
            "not_applicable_n",
            "profile",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "review_record_id": {"type": "string"},
            "checklist_version": {"type": "string"},
            "guideline_version": {"type": "string"},
            "application_prompt_version": {"type": "string"},
            "paper_context_used": {"type": "string", "enum": ["yes", "partial", "no"]},
            "checklist_answers": {"type": "array", "items": answer_schema},
            "dimension_summaries": {"type": "array", "items": dimension_summary_schema},
            "overall_quality_profile": {
                "type": "object",
                "properties": {
                    "main_strengths": {"type": "array", "items": {"type": "string"}},
                    "main_gaps": {"type": "array", "items": {"type": "string"}},
                    "most_informative_items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "caution_notes": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "main_strengths",
                    "main_gaps",
                    "most_informative_items",
                    "caution_notes",
                ],
                "additionalProperties": False,
            },
        },
        "required": [
            "review_record_id",
            "checklist_version",
            "guideline_version",
            "application_prompt_version",
            "paper_context_used",
            "checklist_answers",
            "dimension_summaries",
            "overall_quality_profile",
        ],
        "additionalProperties": False,
    }


def split_anthropic_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """Convert OpenAI-style system/user messages to Anthropic Messages format."""

    system_parts: list[str] = []
    anthropic_messages: list[dict[str, str]] = []
    for message in messages:
        role = message["role"]
        content = message["content"]
        if role in {"system", "developer"}:
            system_parts.append(content)
        elif role in {"user", "assistant"}:
            anthropic_messages.append({"role": role, "content": content})
        else:
            anthropic_messages.append({"role": "user", "content": content})
    return "\n\n".join(system_parts), anthropic_messages


def anthropic_messages_url(base_url: str) -> str:
    if not base_url:
        return "https://api.anthropic.com/v1/messages"
    stripped = base_url.rstrip("/")
    if stripped.endswith("/messages"):
        return stripped
    return f"{stripped}/messages"


def run_one_openai_responses(
    client: OpenAI,
    request: dict[str, Any],
    model: str,
    temperature: float,
) -> tuple[Any, str, bool, str | None, dict[str, Any]]:
    request_kwargs: dict[str, Any] = {
        "model": model,
        "input": request["messages"],
        "temperature": temperature,
    }

    temperature_sent = True
    temperature_retry_reason = None
    try:
        response = client.responses.create(**request_kwargs)
    except BadRequestError as error:
        if not is_unsupported_temperature_error(error):
            raise

        # gpt-5.5 currently does not support temperature. Experiments request 0
        # by default; if rejected, retry without temperature and record the change.
        temperature_sent = False
        temperature_retry_reason = "model_does_not_support_temperature"
        request_kwargs.pop("temperature", None)
        response = client.responses.create(**request_kwargs)

    return response, response.output_text, temperature_sent, temperature_retry_reason, {}


def run_one_deepseek_chat_completion(
    client: OpenAI,
    request: dict[str, Any],
    model: str,
    temperature: float,
    thinking: str,
    reasoning_effort: str,
) -> tuple[Any, str, bool, str | None, dict[str, Any]]:
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": request["messages"],
        "response_format": {"type": "json_object"},
        "extra_body": {"thinking": {"type": thinking}},
    }

    temperature_sent = True
    temperature_retry_reason = None
    if thinking == "enabled":
        # DeepSeek thinking mode ignores sampling controls. Avoid sending
        # temperature so the result metadata reflects the actual request.
        temperature_sent = False
        temperature_retry_reason = "deepseek_thinking_mode_ignores_temperature"
        request_kwargs["reasoning_effort"] = reasoning_effort
    else:
        request_kwargs["temperature"] = temperature

    response = client.chat.completions.create(**request_kwargs)
    message = response.choices[0].message
    raw_text = message.content or ""
    provider_metadata = {
        "deepseek_thinking": thinking,
        "reasoning_effort": reasoning_effort if thinking == "enabled" else None,
        "reasoning_content_present": bool(getattr(message, "reasoning_content", None)),
    }
    return response, raw_text, temperature_sent, temperature_retry_reason, provider_metadata


def run_one_kimi_chat_completion(
    client: OpenAI,
    request: dict[str, Any],
    model: str,
    reasoning_effort: str,
) -> tuple[Any, str, bool, str | None, dict[str, Any]]:
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": request["messages"],
        "response_format": {"type": "json_object"},
        "reasoning_effort": reasoning_effort,
    }

    # Kimi K3 has fixed sampling parameters; do not send temperature.
    temperature_sent = False
    temperature_retry_reason = "kimi_fixed_temperature_not_sent"

    response = client.chat.completions.create(**request_kwargs)
    message = response.choices[0].message
    raw_text = message.content or ""
    provider_metadata = {
        "kimi_reasoning_effort": reasoning_effort,
        "reasoning_content_present": bool(getattr(message, "reasoning_content", None)),
    }
    return response, raw_text, temperature_sent, temperature_retry_reason, provider_metadata


def run_one_anthropic_messages(
    client: SimpleNamespace,
    request: dict[str, Any],
    model: str,
    reasoning_effort: str,
    max_tokens: int,
) -> tuple[Any, str, bool, str | None, dict[str, Any]]:
    system_prompt, messages = split_anthropic_messages(request["messages"])
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "output_config": {
            "effort": reasoning_effort,
            "format": {
                "type": "json_schema",
                "schema": checklist_application_json_schema(),
            },
        },
    }
    if system_prompt:
        payload["system"] = system_prompt

    req = urllib.request.Request(
        anthropic_messages_url(client.base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": client.api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=client.timeout_seconds) as response_file:
            response_body = json.loads(response_file.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic API HTTP {error.code}: {error_body}") from error

    content_blocks = response_body.get("content", [])
    raw_text = "\n".join(
        block.get("text", "") for block in content_blocks if block.get("type") == "text"
    ).strip()
    response = SimpleNamespace(
        id=response_body.get("id"),
        model=response_body.get("model"),
        usage=response_body.get("usage"),
        raw=response_body,
    )
    provider_metadata = {
        "anthropic_reasoning_effort": reasoning_effort,
        "anthropic_max_tokens": max_tokens,
        "anthropic_stop_reason": response_body.get("stop_reason"),
    }
    return (
        response,
        raw_text,
        False,
        "anthropic_sampling_parameters_not_sent",
        provider_metadata,
    )


def run_one_request(
    client: Any,
    request: dict[str, Any],
    model: str,
    temperature: float,
    provider: str,
    deepseek_thinking: str,
    reasoning_effort: str,
    anthropic_max_tokens: int,
) -> dict[str, Any]:
    if provider == "openai":
        response, raw_text, temperature_sent, temperature_retry_reason, provider_metadata = (
            run_one_openai_responses(client, request, model, temperature)
        )
    elif provider == "deepseek":
        response, raw_text, temperature_sent, temperature_retry_reason, provider_metadata = (
            run_one_deepseek_chat_completion(
                client,
                request,
                model,
                temperature,
                deepseek_thinking,
                reasoning_effort,
            )
        )
    elif provider == "kimi":
        response, raw_text, temperature_sent, temperature_retry_reason, provider_metadata = (
            run_one_kimi_chat_completion(
                client,
                request,
                model,
                reasoning_effort,
            )
        )
    elif provider == "anthropic":
        response, raw_text, temperature_sent, temperature_retry_reason, provider_metadata = (
            run_one_anthropic_messages(
                client,
                request,
                model,
                reasoning_effort,
                anthropic_max_tokens,
            )
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    parsed_json, parse_error = parse_model_json(raw_text)

    result = {
        "request_id": request["request_id"],
        "task": request["task"],
        "prompt_version": request["prompt_version"],
        "provider": provider,
        "model": model,
        "model_returned": getattr(response, "model", None),
        "temperature_requested": temperature,
        "temperature_sent": temperature_sent,
        "temperature_retry_reason": temperature_retry_reason,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "response_id": getattr(response, "id", None),
        "usage": serialise_usage(response),
        "source": request["source"],
        "raw_output_text": raw_text,
        "parsed_output_json": parsed_json,
        "parse_error": parse_error,
    }
    result.update(provider_metadata)
    return result


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_jsonl(record: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def completed_request_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {record["request_id"] for record in read_jsonl(path) if record.get("request_id")}


def safe_filename_value(value: str) -> str:
    return value.replace("/", "_").replace(":", "_").replace(" ", "_")


def output_model_label(args: argparse.Namespace) -> str:
    label = safe_filename_value(args.model)
    if args.provider == "deepseek":
        label = f"{label}_thinking-{args.deepseek_thinking}"
        if args.deepseek_thinking == "enabled":
            label = f"{label}_effort-{args.reasoning_effort}"
    elif args.provider in {"kimi", "anthropic"}:
        label = f"{label}_effort-{args.reasoning_effort}"
    return label


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run JSONL requests for LLM-assisted open coding.")
    parser.add_argument("--request-path", default=DEFAULT_REQUEST_PATH, help="Path to the request JSONL.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for result JSONL files.")
    parser.add_argument(
        "--provider",
        choices=["openai", "deepseek", "kimi", "anthropic"],
        default="openai",
        help="API provider; defaults to openai to preserve the existing Responses API behaviour.",
    )
    parser.add_argument("--model", default="gpt-5.5", help="ID of the model to call.")
    parser.add_argument(
        "--api-key-env",
        default="",
        help=(
            "Name of the API-key environment variable. Defaults: DEEPSEEK_API_KEY for DeepSeek, "
            "MOONSHOT_API_KEY for Kimi, and ANTHROPIC_API_KEY for Anthropic. OpenAI uses the "
            "existing SDK configuration by default."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="",
        help=(
            "Provider base URL. Defaults: https://api.deepseek.com for DeepSeek, "
            "https://api.moonshot.cn/v1 for Kimi, and https://api.anthropic.com/v1 for Anthropic."
        ),
    )
    parser.add_argument(
        "--deepseek-thinking",
        choices=["enabled", "disabled"],
        default="enabled",
        help="DeepSeek thinking-mode switch; used only with --provider deepseek.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "high", "max"],
        default="high",
        help="Reasoning effort for DeepSeek thinking mode, Kimi K3, or Anthropic; defaults to high.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help=(
            "Generation temperature to request; defaults to 0. If unsupported, retry without the "
            "parameter and record the change."
        ),
    )
    parser.add_argument("--limit", type=int, default=3, help="Maximum requests to run; defaults to 3.")
    parser.add_argument("--dry-run", action="store_true", help="Validate requests without calling an API.")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not skip requests already completed in the result file.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Number of concurrent API requests; defaults to 1 and may be increased for batch runs.",
    )
    parser.add_argument(
        "--anthropic-max-tokens",
        type=int,
        default=64000,
        help="Anthropic Messages API max_tokens; Claude 5 thinking counts toward this limit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request_path = Path(args.request_path)
    output_dir = Path(args.output_dir)

    requests = read_jsonl(request_path)
    if args.limit > 0:
        requests = requests[: args.limit]

    request_stem = request_path.stem
    model_label = output_model_label(args)
    output_path = output_dir / f"{request_stem}_results_{model_label}_temp{args.temperature}.jsonl"
    done_ids = set() if args.no_resume else completed_request_ids(output_path)
    selected_ids = {request["request_id"] for request in requests}
    done_selected_ids = selected_ids & done_ids
    pending_requests = [request for request in requests if request["request_id"] not in done_selected_ids]

    summary = {
        "request_path": str(request_path),
        "output_path": str(output_path),
        "requests_total_selected": len(requests),
        "requests_already_completed": len(done_selected_ids),
        "requests_to_run": len(pending_requests),
        "provider": args.provider,
        "model": args.model,
        "temperature_requested": args.temperature,
        "deepseek_thinking": args.deepseek_thinking if args.provider == "deepseek" else None,
        "reasoning_effort": (
            args.reasoning_effort
            if (
                (args.provider == "deepseek" and args.deepseek_thinking == "enabled")
                or args.provider in {"kimi", "anthropic"}
            )
            else None
        ),
        "anthropic_max_tokens": (
            args.anthropic_max_tokens if args.provider == "anthropic" else None
        ),
        "max_workers": args.max_workers,
        "dry_run": args.dry_run,
        "resume": not args.no_resume,
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if args.max_workers < 1:
        raise ValueError("--max-workers must be at least 1.")

    if args.provider == "deepseek":
        api_key_env = args.api_key_env or "DEEPSEEK_API_KEY"
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing DeepSeek API key environment variable: {api_key_env}")
        client = OpenAI(api_key=api_key, base_url=args.base_url or "https://api.deepseek.com")
    elif args.provider == "kimi":
        api_key_env = args.api_key_env or "MOONSHOT_API_KEY"
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing Kimi API key environment variable: {api_key_env}")
        client = OpenAI(api_key=api_key, base_url=args.base_url or "https://api.moonshot.cn/v1")
    elif args.provider == "anthropic":
        api_key_env = args.api_key_env or "ANTHROPIC_API_KEY"
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing Anthropic API key environment variable: {api_key_env}")
        client = SimpleNamespace(
            api_key=api_key,
            base_url=args.base_url or "https://api.anthropic.com/v1",
            timeout_seconds=3600,
        )
    else:
        client = OpenAI()

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(
                run_one_request,
                client,
                request,
                args.model,
                args.temperature,
                args.provider,
                args.deepseek_thinking,
                args.reasoning_effort,
                args.anthropic_max_tokens,
            ): request["request_id"]
            for request in pending_requests
        }
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            append_jsonl(result, output_path)
            print(
                json.dumps(
                    {
                        "completed_this_run": index,
                        "remaining_this_run": len(pending_requests) - index,
                        "request_id": result["request_id"],
                        "parsed": result["parsed_output_json"] is not None,
                        "parse_error": result["parse_error"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    results = read_jsonl(output_path) if output_path.exists() else []
    selected_results = [result for result in results if result.get("request_id") in selected_ids]
    parsed_count = sum(result["parsed_output_json"] is not None for result in selected_results)
    summary["parsed_json_count"] = parsed_count
    summary["parse_error_count"] = len(selected_results) - parsed_count
    summary["temperature_sent_count"] = sum(result["temperature_sent"] for result in selected_results)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
