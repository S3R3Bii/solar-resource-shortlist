"""Capture each bounded official request once before parsing,retaining every failure."""

import argparse, hashlib, json, platform, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--private-dir", type=Path, required=True)
    a = p.parse_args()
    a.private_dir.mkdir(parents=True, exist_ok=False)
    receipts = []
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    for r in json.loads(
        (ROOT / "data/source_requests.json").read_text(encoding="utf-8")
    ):
        started = datetime.now(timezone.utc).isoformat()
        body = b""
        status = None
        headers = {}
        error = None
        try:
            with urlopen(
                Request(
                    r["url"],
                    headers={"User-Agent": "IndependentSolarResourceResearch/1.0"},
                ),
                timeout=120,
            ) as response:
                status = response.status
                headers = dict(response.headers.items())
                body = response.read()
        except HTTPError as exc:
            status = exc.code
            headers = dict(exc.headers.items())
            body = exc.read()
            error = str(exc)
        except Exception as exc:
            error = type(exc).__name__ + ":" + str(exc)
        (a.private_dir / r["file"]).write_bytes(body)
        item = dict(
            r,
            started_utc=started,
            completed_utc=datetime.now(timezone.utc).isoformat(),
            status=status,
            headers={
                k: v
                for k, v in headers.items()
                if k.lower()
                in [
                    "content-type",
                    "content-length",
                    "last-modified",
                    "etag",
                    "date",
                    "x-amzn-requestid",
                ]
            },
            bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            protocol_commit=commit,
            python=platform.python_version(),
            error=error,
        )
        receipts.append(item)
        (a.private_dir / "requests.json").write_bytes(
            (json.dumps(receipts, indent=2) + "\n").encode()
        )
        print(
            json.dumps(
                {k: item[k] for k in ["point", "format", "status", "bytes", "error"]}
            ),
            flush=True,
        )
        assert (
            status == 200 and error is None
        ), "Preserved source failure;stop collection without bypass or silent retry"
        time.sleep(1)
    print("CAPTURE_COMPLETE", len(receipts), flush=True)


if __name__ == "__main__":
    main()
