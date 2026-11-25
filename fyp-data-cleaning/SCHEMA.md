# Data cleaning: Phase 2 starter contract

Status: initial, lossless S3 audit ingestion contract. This is not the final detector-input schema and does not define sender/receiver joins.

## Observed input

The inventory found gzip-compressed JSON files under the earlier PoC folder’s `poc-data/cloudtrail-logs/`. Each inspected document used a root `Records` array. The parser detects compression by the gzip signature and accepts JSON arrays, single JSON objects, and line-delimited JSON so it does not depend on filenames alone.

The observed audit records include `eventID`, `eventTime`, `eventSource`, `eventName`, `requestParameters`, `userIdentity`, `sourceIPAddress`, and `additionalEventData`. `requestParameters.key` was absent in one observed shape. Parsed event objects are preserved as-is inside an output envelope; the parser does not flatten or rename event fields.

## Output envelope

`audit-events.jsonl` contains one envelope per accepted event:

- `parser_version`: parser version string
- `source_file`: path relative to the input directory
- `record_index`: zero-based JSON array index, or zero-based JSONL line index
- `line_number`: one-based line number for JSONL inputs
- `origin`: `unknown` until source origin is established from evidence
- `warnings`: non-destructive missing/type/timestamp observations
- `event`: complete parsed event object

`quarantine.jsonl` records malformed inputs, non-object records, and objects lacking string `eventName` or `eventSource`, with source and record/line provenance where available. Raw inputs remain untouched. The source path and location let a reviewer inspect quarantined content in the raw file.

## Handling decisions

- Missing and null fields remain in the event as found; no replacement values are invented.
- Timestamp strings are retained unchanged. Invalid or timezone-naive timestamps are flagged; they are not interpreted as UTC.
- Unexpected event fields remain in the full event object.
- No deduplication is performed. `eventID` is observed on all currently inventoried audit records, but uniqueness and replay semantics must be reviewed before choosing a deduplication policy.
- No cross-source joins are performed. The audit records have no observed `run_id`.
- No receiver records, receiver-derived fields, payload digests, or scenario labels are added to this output.
- `origin` stays `unknown`; a CloudTrail-style filename alone does not establish emulator versus simulated origin.

## Current run scope

The existing sample output was generated from the earlier PoC folder’s `poc-data/cloudtrail-logs/`; it is not the planned full experiment dataset. The standalone parser requires explicit `--input-dir` and `--output-dir` arguments so it does not depend on that old project folder. It refuses to overwrite a non-empty output directory.

The next schema decision is the sender-side outbound telemetry contract, especially where a run ID and request sequence are recorded and how the receiver independently stores the run ID. Audit-to-run correlation remains unavailable unless collection provides a trustworthy link.
