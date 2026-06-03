"""Prepare a small library of public, safe demo images and upload to the demo bucket.

We intentionally avoid shipping test images in git. This script downloads a
handful of Wikimedia Commons images that sit on the 'edge' (gym, yoga, art,
mild violence in games) — the kinds of images clients want to see
jurisdiction policies diverge on. URLs are CC-licensed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import urllib.request

import boto3

from ugc_moderation.settings import get_settings

_UA = "Mozilla/5.0 (UGCModerationAgentDemo/0.1)"

# picsum.photos serves stable seeded Lorem Picsum stock photos; no auth, no rate issues.
# These are baseline compliant images — for Demo we want the real AWS call chain to run.
# Real "edge" samples should come from the customer's own desensitized set during the pitch.
SAMPLES = [
    ("sunset_lake.jpg",  "https://picsum.photos/seed/sunset-lake/640/480",
     "Landscape baseline (compliant)"),
    ("city_street.jpg",  "https://picsum.photos/seed/city-street/640/480",
     "Urban street scene"),
    ("coffee_cup.jpg",   "https://picsum.photos/seed/coffee-cup/640/480",
     "Object close-up — non-sensitive"),
    ("abstract_art.jpg", "https://picsum.photos/seed/abstract-art/640/480",
     "Abstract pattern — exercises label-free path"),
]

LOCAL_DIR = Path(__file__).resolve().parents[1] / "streamlit_app" / "assets" / "benchmark"


def main() -> int:
    s = get_settings()
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    s3 = boto3.client("s3", region_name=s.aws_region)

    for name, url, desc in SAMPLES:
        local = LOCAL_DIR / name
        if not local.exists():
            print(f"  download {name} ...")
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                local.write_bytes(resp.read())
        key = f"demo/{name}"
        s3.upload_file(str(local), s.demo_bucket, key, ExtraArgs={"ContentType": "image/jpeg"})
        print(f"    -> s3://{s.demo_bucket}/{key}  ({desc})")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
