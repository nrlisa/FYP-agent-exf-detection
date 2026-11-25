# Draft: run ID and telemetry contract

Status: proposed for team review; not yet implemented. This describes what the full experiment should collect. It does not change the PoC code or current logs.

## The simple rule

Make one unique `run_id` before each experiment run starts. Use that same ID in the agent's sender log and the receiver's separate evaluation log. This lets the team match records from the same run without guessing from timestamps.

## Sender-side activity log (monitor may read)

Write one JSON object per HTTP request to a JSONL file. For chunked transfers, write one object per chunk and increase `sequence` each time.

Proposed fields:

- `run_id`: ID created before the run
- `sequence`: request number within the run, starting at 1
- `agent_id`: identifier, or null if unavailable
- `observed_at`: timestamp with timezone included
- `method`: HTTP method
- `destination_host`, `destination_port`, `destination_path`: where the request went
- `status`: HTTP response status code, or null if the request failed before a response

Record sender-side application-level HTTP metadata only. Do not put the request body, payload content, byte count, `request_size_bytes` (or any request-size field), secret data, scenario name, or a pre-computed `approved` / `suspicious` decision in this log or in monitor inputs.

## Receiver ground-truth log (evaluation only)

The receiver should record the same `run_id` and `sequence`, plus whether it received the request, received bytes, SHA-256 payload digest, and whether the expected synthetic data was fully received. Keep this file separate from monitor inputs. The evaluation step can read it after the monitor has saved its decision.

Do not copy receiver records, receiver sizes, payload digests, success labels, or scenario labels into the sender log or monitor input.

## S3 audit records

Keep each audit event's own `eventID`, source filename, and record position. The current PoC audit records do not contain a `run_id`, so do not join them to a run by guessing timestamps alone without a documented correlation rule.

A possible way to test is adding a run marker to the S3 client's user-agent (e.g. via `botocore` `user_agent_extra`) and checking whether Floci writes that marker into `event.userAgent`. This is only a proposal: use the join only if a small collection check shows the marker is present and reliable. Otherwise keep audit events unjoined or use a documented time-window rule, and report that limit.

In Phase 2 (monitor-input normalisation), deduplicate repeated `eventID` records, separate or filter audit-delivery self-writes (e.g. `userAgent == "cloudtrail.amazonaws.com"` `PutObject` into `AWSLogs/`), and exclude byte-count fields (`bytesTransferredOut`, `bytesTransferredIn`) from monitor inputs.

## What monitors receive

All three monitors (M1 static rules, M2 behavioural-baseline, M3 local LLM) must receive identical normalised evidence within each configuration:

- **Configuration A (S3 audit-only):** normalised S3 audit metadata only (e.g. `event_time`, `event_name`, `principal`, `bucket`, `object_key`, `source_ip`, and `run_id` where verified).
- **Configuration B (Correlated S3 + HTTP):** the same normalised S3 audit metadata plus sender-side HTTP activity metadata, plus the shared approved-destination policy.

Monitors must **not** receive the receiver ground-truth file, `bytesTransferredOut` / `bytesTransferredIn` / request-size or byte-count fields, payload content or digests, scenario manifest, scenario name, secret data, or transfer-success labels.

## Before real data collection

The team should agree on these fields, implement the run ID in the experiment runner, sender, and receiver, then collect a small pilot and inspect the actual saved records. Only after verifying the shared sender/receiver ID should the full experiment use it for joins.
