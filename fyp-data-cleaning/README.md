# FYP data cleaning starter

This is a separate starter project for the FYP data-cleaning pipeline. It contains a lossless first-pass parser for S3 audit evidence and a sample output generated from the existing PoC logs. The full experiment dataset has not yet been collected.

## Run the audit parser

Pass the raw audit folder and a new output folder explicitly:

```powershell
python clean_s3_audit.py --input-dir "PATH_TO_RAW_AUDIT_LOGS" --output-dir "derived/your-run-name"
```

The parser reads raw inputs without modifying them. It writes `audit-events.jsonl` and `quarantine.jsonl` beneath the selected output folder. It does not deduplicate events, infer timezone information, join telemetry sources, or build monitor inputs.

The existing `derived/poc-audit-v1/` files are a sample from the earlier PoC. Keep them labelled as PoC data; they are not full experiment results.
