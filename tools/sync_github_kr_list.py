#!/usr/bin/env python3
"""Sync repositories from etashi04's public GitHub KR List."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "github-kr-list.json"
LIST_URL = "https://github.com/stars/etashi04/lists/kr-list"
API_ROOT = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "http-etashi-kr-list-sync",
    "X-GitHub-Api-Version": "2022-11-28",
}


def fetch_text(url: str) -> str:
    with urlopen(Request(url, headers=HEADERS), timeout=30) as response:
        return response.read().decode("utf-8")


def fetch_json(url: str) -> dict[str, object]:
    return json.loads(fetch_text(url))


def has_release(full_name: str) -> bool:
    try:
        fetch_json(f"{API_ROOT}/repos/{full_name}/releases/latest")
        return True
    except HTTPError as error:
        if error.code == 404:
            return False
        raise


def main() -> None:
    html = fetch_text(LIST_URL)
    full_names = list(dict.fromkeys(
        f"{owner}/{repo}"
        for owner, repo in re.findall(
            r'<h2 class="h3">\s*<a href="/([^/\"]+)/([^/\"?#]+)">',
            html,
            re.S,
        )
    ))
    if not full_names:
        raise RuntimeError("KR List에서 저장소를 찾지 못했습니다.")

    repositories = []
    for full_name in full_names:
        repo = fetch_json(f"{API_ROOT}/repos/{full_name}")
        repo["has_release"] = has_release(full_name)
        repositories.append(repo)

    repositories.sort(key=lambda repo: str(repo.get("updated_at", "")), reverse=True)
    OUTPUT_PATH.write_text(
        json.dumps(repositories, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"GitHub KR List synchronized: {len(repositories)}")


if __name__ == "__main__":
    main()
