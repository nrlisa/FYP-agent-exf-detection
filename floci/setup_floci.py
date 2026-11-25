#!/usr/bin/env python3
"""Idempotent Floci setup for the FYP controlled cloud testbed.

Matches the verified PoC environment:
- Floci S3 / CloudTrail / IAM endpoint on http://localhost:4567 (us-east-1)
- Buckets: fyp-persistence-test (audit delivery), fyp-experiment-data (source),
  and fyp-exfil-sink
- CloudTrail trail: fyp-poc-trail with S3 object-level data selectors
- IAM user: experiment-agent with read access to fyp-experiment-data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

DEFAULT_ENDPOINT = "http://localhost:4567"
REGION = "us-east-1"
AUDIT_BUCKET = "fyp-persistence-test"
SOURCE_BUCKET = "fyp-experiment-data"
SINK_BUCKET = "fyp-exfil-sink"
TRAIL_NAME = "fyp-poc-trail"
AGENT_USER = "experiment-agent"
SAMPLE_KEY = "synthetic/experiment-test-data.txt"
SAMPLE_PAYLOAD = (
    b"SYNTHETIC TEST DATA ONLY\n"
    b"Record A: demo-value-001\n"
    b"Record B: demo-value-002\n"
)

AGENT_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ListExperimentBucket",
            "Effect": "Allow",
            "Action": "s3:ListBucket",
            "Resource": f"arn:aws:s3:::{SOURCE_BUCKET}",
        },
        {
            "Sid": "ReadExperimentObjects",
            "Effect": "Allow",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{SOURCE_BUCKET}/*",
        },
    ],
}


def ensure_bucket(s3, bucket: str) -> str:
    try:
        s3.head_bucket(Bucket=bucket)
        return "exists"
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        return "created"


def ensure_sample_object(s3) -> str:
    try:
        s3.head_object(Bucket=SOURCE_BUCKET, Key=SAMPLE_KEY)
        return "exists"
    except ClientError:
        s3.put_object(Bucket=SOURCE_BUCKET, Key=SAMPLE_KEY, Body=SAMPLE_PAYLOAD)
        return "uploaded"


def ensure_trail(ct) -> str:
    trails = ct.describe_trails(trailNameList=[TRAIL_NAME]).get("trailList", [])
    if any(t.get("Name") == TRAIL_NAME for t in trails):
        status = "exists"
    else:
        ct.create_trail(
            Name=TRAIL_NAME,
            S3BucketName=AUDIT_BUCKET,
            IncludeGlobalServiceEvents=True,
        )
        status = "created"

    ct.put_event_selectors(
        TrailName=TRAIL_NAME,
        EventSelectors=[
            {
                "ReadWriteType": "All",
                "IncludeManagementEvents": True,
                "DataResources": [
                    {
                        "Type": "AWS::S3::Object",
                        "Values": [
                            f"arn:aws:s3:::{AUDIT_BUCKET}/",
                            f"arn:aws:s3:::{SOURCE_BUCKET}/",
                            f"arn:aws:s3:::{SINK_BUCKET}/",
                        ],
                    }
                ],
            }
        ],
    )
    ct.start_logging(Name=TRAIL_NAME)
    return status


def ensure_agent_user(iam, env_out: Path) -> tuple[str, str | None]:
    try:
        iam.get_user(UserName=AGENT_USER)
        user_status = "exists"
    except ClientError:
        iam.create_user(UserName=AGENT_USER)
        user_status = "created"

    iam.put_user_policy(
        UserName=AGENT_USER,
        PolicyName="ExperimentAgentRead",
        PolicyDocument=json.dumps(AGENT_POLICY),
    )

    keys = iam.list_access_keys(UserName=AGENT_USER).get("AccessKeyMetadata", [])
    if keys:
        return user_status, f"already has {len(keys)} key(s) (id={keys[0]['AccessKeyId']})"

    created = iam.create_access_key(UserName=AGENT_USER)["AccessKey"]
    env_text = (
        f"EXPERIMENT_AGENT_ACCESS_KEY={created['AccessKeyId']}\n"
        f"EXPERIMENT_AGENT_SECRET_KEY={created['SecretAccessKey']}\n"
    )
    if not env_out.exists():
        env_out.write_text(env_text, encoding="utf-8")
        return user_status, f"created key saved to {env_out}"
    return user_status, f"created key (id={created['AccessKeyId']}; {env_out} left unchanged)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT)
    parser.add_argument(
        "--env-out",
        type=Path,
        default=Path(__file__).with_name(".env.generated"),
        help="Where to write newly created experiment-agent keys if absent.",
    )
    args = parser.parse_args()

    cfg = Config(s3={"addressing_style": "path"})
    session = boto3.session.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=REGION,
    )
    sts = session.client("sts", endpoint_url=args.endpoint_url)
    s3 = session.client("s3", endpoint_url=args.endpoint_url, config=cfg)
    ct = session.client("cloudtrail", endpoint_url=args.endpoint_url)
    iam = session.client("iam", endpoint_url=args.endpoint_url)

    caller = sts.get_caller_identity()
    buckets = {b: ensure_bucket(s3, b) for b in (AUDIT_BUCKET, SOURCE_BUCKET, SINK_BUCKET)}
    obj_status = ensure_sample_object(s3)
    trail_status = ensure_trail(ct)
    trail_logging = ct.get_trail_status(Name=TRAIL_NAME).get("IsLogging")
    user_status, key_info = ensure_agent_user(iam, args.env_out)

    print(
        json.dumps(
            {
                "endpoint_url": args.endpoint_url,
                "account": caller.get("Account"),
                "buckets": buckets,
                "sample_object": {f"{SOURCE_BUCKET}/{SAMPLE_KEY}": obj_status},
                "trail": {"name": TRAIL_NAME, "status": trail_status, "is_logging": trail_logging},
                "iam_user": {"name": AGENT_USER, "status": user_status, "keys": key_info},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
