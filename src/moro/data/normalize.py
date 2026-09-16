import json
from typing import Any

from moro.core.hashing import sha256_text
from moro.data.models import DatasetMessage, DatasetRow, InvalidRow

VALID_ROLES = {"system", "user", "assistant"}


def normalize_rows(
    raw_rows: list[dict],
    source_name: str,
) -> tuple[list[DatasetRow], list[InvalidRow]]:
    """
    Convert raw ingested rows into normalized DatasetRow objects.

    Supports three input formats:
    1. messages  — OpenAI chat format with a 'messages' list
    2. instruction/input/output — Alpaca-style instruction tuning
    3. prompt/completion — simple two-field format

    Returns (valid_rows, invalid_rows).
    """
    valid_rows: list[DatasetRow] = []
    invalid_rows: list[InvalidRow] = []

    for raw in raw_rows:
        source_file = raw.get("_source_file", source_name)
        line_number = raw.get("_line_number")

        try:
            messages = _normalize_single_row(raw)

            if not messages:
                invalid_rows.append(
                    InvalidRow(
                        source=str(source_file),
                        line_number=line_number,
                        reason="No valid messages could be extracted",
                        raw=_clean_raw(raw),
                    )
                )
                continue

            row_id = _make_row_id(messages)

            valid_rows.append(
                DatasetRow(
                    id=row_id,
                    source=str(source_file),
                    messages=messages,
                    metadata={
                        "source_file": str(source_file),
                        "line_number": line_number,
                        "format": raw.get("_format"),
                    },
                )
            )

        except Exception as exc:
            invalid_rows.append(
                InvalidRow(
                    source=str(source_file),
                    line_number=line_number,
                    reason=str(exc),
                    raw=_clean_raw(raw),
                )
            )

    return valid_rows, invalid_rows


def _clean_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Strip internal metadata keys."""
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _make_row_id(messages: list[DatasetMessage]) -> str:
    canonical = json.dumps(
        [m.model_dump() for m in messages],
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"row_{sha256_text(canonical)[:16]}"


def _normalize_single_row(raw: dict[str, Any]) -> list[DatasetMessage]:
    system_text = str(raw.get("system", "")).strip()

    # 1) Native messages format
    if "messages" in raw and isinstance(raw["messages"], list):
        messages = _parse_messages_list(raw["messages"])
        if system_text and not any(m.role == "system" for m in messages):
            messages.insert(0, DatasetMessage(role="system", content=system_text))
        return messages

    # 2) Alpaca instruction/input/output
    instruction = str(raw.get("instruction", "")).strip()
    output = _extract_completion(raw)

    if instruction:
        if not output:
            raise ValueError("instruction row is missing output/completion")
        instruction_input = str(raw.get("input", "")).strip()
        user_content = f"{instruction}\n\n{instruction_input}" if instruction_input else instruction
        messages: list[DatasetMessage] = []
        if system_text:
            messages.append(DatasetMessage(role="system", content=system_text))
        messages += [
            DatasetMessage(role="user", content=user_content),
            DatasetMessage(role="assistant", content=output),
        ]
        return messages

    # 3) Prompt/completion
    prompt = _extract_prompt(raw)
    completion = _extract_completion(raw)
    if prompt and completion:
        messages = []
        if system_text:
            messages.append(DatasetMessage(role="system", content=system_text))
        messages += [
            DatasetMessage(role="user", content=prompt),
            DatasetMessage(role="assistant", content=completion),
        ]
        return messages

    # 4) Text-only — not usable for SFT
    if "text" in raw:
        raise ValueError(
            "text-only row cannot be used for supervised fine-tuning; "
            "use messages, instruction/output, or prompt/completion format"
        )

    raise ValueError("Unrecognized row format — no messages, instruction, or prompt found")


def _parse_messages_list(messages_raw: list[Any]) -> list[DatasetMessage]:
    messages: list[DatasetMessage] = []
    for msg in messages_raw:
        if not isinstance(msg, dict):
            raise ValueError("Each message must be a dict")
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid message role: {role!r}")
        if not content:
            raise ValueError(f"Empty content for role: {role!r}")
        messages.append(DatasetMessage(role=role, content=content))
    return messages


def _extract_prompt(raw: dict[str, Any]) -> str:
    for key in ("prompt", "question", "query", "input"):
        v = raw.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _extract_completion(raw: dict[str, Any]) -> str:
    for key in ("completion", "output", "response", "answer", "completion_text", "target"):
        v = raw.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""
