#!/usr/bin/env python3
"""Lossless first-pass parser for observed S3 audit evidence.

Raw files are read only. Outputs are provenance-wrapped JSONL plus quarantine.
No deduplication, timezone assumptions, cross-source joins, or monitor inputs.
"""
from __future__ import annotations
import argparse
import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PARSER_VERSION = "0.1.0"


def read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        payload = path.read_bytes()
        if payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
        return payload.decode("utf-8-sig"), None
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def timestamp_warnings(event: dict[str, Any]) -> list[str]:
    value = event.get("eventTime")
    if value is None:
        return ["missing_or_null:eventTime"]
    if not isinstance(value, str):
        return ["unexpected_type:eventTime"]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ["invalid:eventTime"]
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return ["timezone_naive:eventTime"]
    return []


def event_warnings(event: dict[str, Any]) -> list[str]:
    warnings = []
    for key in ("eventID", "eventTime", "eventSource", "eventName"):
        if key not in event or event[key] is None:
            warnings.append(f"missing_or_null:{key}")
    for key in ("eventSource", "eventName"):
        if key in event and event[key] is not None and not isinstance(event[key], str):
            warnings.append(f"unexpected_type:{key}")
    warnings.extend(timestamp_warnings(event))
    for parent, child in (("requestParameters", "bucketName"),
                          ("requestParameters", "key"),
                          ("userIdentity", "arn")):
        value = event.get(parent)
        if value is not None and not isinstance(value, dict):
            warnings.append(f"unexpected_type:{parent}")
        elif isinstance(value, dict) and child in value and value[child] is not None and not isinstance(value[child], str):
            warnings.append(f"unexpected_type:{parent}.{child}")
    return sorted(set(warnings))


def quarantine(source: str, reason: str, index=None, line=None, detail=None):
    item = {"parser_version": PARSER_VERSION, "source_file": source, "reason": reason}
    if index is not None:
        item["record_index"] = index
    if line is not None:
        item["line_number"] = line
    if detail:
        item["detail"] = str(detail)[:500]
    return item


def candidates(text: str, source: str):
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        for line_no, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                yield None, line_no - 1, line_no, quarantine(source, "blank_line", line=line_no)
                continue
            try:
                yield json.loads(line), line_no - 1, line_no, None
            except json.JSONDecodeError as exc:
                yield None, line_no - 1, line_no, quarantine(
                    source, "malformed_json_line", line=line_no,
                    detail=f"column {exc.colno}: {exc.msg}")
        return
    if isinstance(document, dict) and "Records" in document:
        records = document["Records"]
        if not isinstance(records, list):
            yield None, None, None, quarantine(source, "Records_not_array")
            return
        for index, item in enumerate(records):
            yield item, index, None, None
    elif isinstance(document, list):
        for index, item in enumerate(document):
            yield item, index, None, None
    elif isinstance(document, dict):
        yield document, 0, None, None
    else:
        yield None, None, None, quarantine(source, "unexpected_document_type", detail=type(document).__name__)


def clean(input_dir: Path, output_dir: Path) -> dict[str, int]:
    input_dir, output_dir = input_dir.resolve(), output_dir.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist: {input_dir}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output: {output_dir}")
    files = sorted(path for path in input_dir.rglob("*") if path.is_file())
    if not files:
        raise SystemExit(f"No input files found under: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {"files_seen": 0, "files_unreadable": 0, "records_written": 0,
              "records_with_warnings": 0, "quarantined": 0}
    with (output_dir / "audit-events.jsonl").open("w", encoding="utf-8", newline="\n") as records_out, \
         (output_dir / "quarantine.jsonl").open("w", encoding="utf-8", newline="\n") as quarantine_out:
        for path in files:
            counts["files_seen"] += 1
            source = path.relative_to(input_dir).as_posix()
            text, error = read_text(path)
            if error:
                counts["files_unreadable"] += 1
                quarantine_out.write(json.dumps(quarantine(source, "unreadable_input", detail=error)) + "\n")
                counts["quarantined"] += 1
                continue
            for item, index, line_no, issue in candidates(text or "", source):
                if issue:
                    quarantine_out.write(json.dumps(issue, ensure_ascii=False) + "\n")
                    counts["quarantined"] += 1
                    continue
                if not isinstance(item, dict):
                    issue = quarantine(source, "unexpected_record_type", index, line_no, type(item).__name__)
                    quarantine_out.write(json.dumps(issue, ensure_ascii=False) + "\n")
                    counts["quarantined"] += 1
                    continue
                if not isinstance(item.get("eventName"), str) or not isinstance(item.get("eventSource"), str):
                    issue = quarantine(source, "missing_or_invalid_event_identity", index, line_no)
                    quarantine_out.write(json.dumps(issue, ensure_ascii=False) + "\n")
                    counts["quarantined"] += 1
                    continue
                warnings = event_warnings(item)
                envelope = {"parser_version": PARSER_VERSION, "source_file": source,
                            "record_index": index, "origin": "unknown",
                            "warnings": warnings, "event": item}
                if line_no is not None:
                    envelope["line_number"] = line_no
                records_out.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
                counts["records_written"] += 1
                counts["records_with_warnings"] += bool(warnings)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Directory of raw audit logs (read only).")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New directory for derived JSONL outputs.")
    args = parser.parse_args()
    result = clean(args.input_dir, args.output_dir)
    print(json.dumps({"input_dir": str(args.input_dir.resolve()),
                      "output_dir": str(args.output_dir.resolve()), **result}, indent=2))


if __name__ == "__main__":
    main()
