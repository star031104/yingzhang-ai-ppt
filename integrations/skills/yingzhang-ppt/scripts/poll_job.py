#!/usr/bin/env python3
"""Poll a YingZhang background job until it finishes (stdlib only).

Usage: python poll_job.py <job_id> [--timeout 900] [--interval 3]
Base URL: $YINGZHANG_API_URL (default http://127.0.0.1:8000). Exit code 0 only when completed.
"""

import argparse
import json
import os
import sys
import time
import urllib.request

TERMINAL = {"completed", "failed", "cancelled"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--interval", type=float, default=3)
    args = parser.parse_args()
    base = os.environ.get("YINGZHANG_API_URL", "http://127.0.0.1:8000").rstrip("/")
    deadline = time.monotonic() + args.timeout
    last = None
    while True:
        with urllib.request.urlopen(f"{base}/api/v1/jobs/{args.job_id}", timeout=30) as response:
            job = json.load(response)
        checkpoint = job.get("checkpoint") or {}
        line = f"{job['status']:<10} {float(job.get('progress') or 0):>5.0%}  {checkpoint.get('label', '')}"
        if line != last:
            print(line, file=sys.stderr, flush=True)
            last = line
        if job["status"] in TERMINAL or time.monotonic() > deadline:
            print(json.dumps({"status": job["status"], "error": job.get("error"),
                              "result": checkpoint.get("result")}, ensure_ascii=False))
            return 0 if job["status"] == "completed" else 1
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
