# Shared Floci Testbed Setup

Reproduces the verified Floci `2.3.0` emulator configuration from the PoC (`floci-persistent`) for team consistency.

## Quick Start (for Nadiah / a fresh laptop)

Prerequisites: Docker Desktop running, Python with `boto3` installed (`pip install boto3`).

1. Start Floci on `http://localhost:4567`:

   ```powershell
   docker compose up -d
   ```

2. Create the buckets, CloudTrail trail (`fyp-poc-trail`), synthetic test object, and `experiment-agent` IAM user:

   ```powershell
   python setup_floci.py
   ```

   If `experiment-agent` does not have an access key yet, `setup_floci.py` writes `.env.generated` in this folder (rename or copy its values to `.env` for the agent script).

## Important Note for Lisa (Existing Container)

If you already have `floci-persistent` running on port `4567`, **do not run `docker compose up -d`** while it is running (it will conflict on port `4567`). Preserve your existing PoC container/buckets or run `python setup_floci.py` in read-safe idempotent mode only after verifying your current container state.
