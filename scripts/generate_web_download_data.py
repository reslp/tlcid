#!/usr/bin/env python3
"""Generate web/download-data.json from latest GitHub releases.

This is a build/deploy-time generator. It only writes files in the local
workspace/build environment and does NOT create git commits.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "docs" / "download-data.json"

APP_URL = "https://api.github.com/repos/reslp/tlcid/releases/latest"
DB_URL = "https://api.github.com/repos/reslp/tlcid-database/releases/latest"


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "tlcid-web-download-data-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def simplify_release(release: dict) -> dict:
    return {
        "tag_name": release.get("tag_name"),
        "name": release.get("name"),
        "html_url": release.get("html_url"),
        "published_at": release.get("published_at"),
        "assets": [
            {
                "name": a.get("name"),
                "size": a.get("size"),
                "browser_download_url": a.get("browser_download_url"),
            }
            for a in release.get("assets", [])
        ],
    }


def main() -> None:
    app_release = fetch_json(APP_URL)
    db_release = fetch_json(DB_URL)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app": simplify_release(app_release),
        "database": simplify_release(db_release),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"App tag: {output['app']['tag_name']}")
    print(f"DB tag:  {output['database']['tag_name']}")


if __name__ == "__main__":
    main()
