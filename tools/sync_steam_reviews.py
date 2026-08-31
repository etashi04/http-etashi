#!/usr/bin/env python3
"""Steam 큐레이터 평가를 사이트 데이터와 script.js에 동기화한다."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "steam-reviews.json"
JS_DATA_PATH = ROOT / "steam-reviews.js"
SCRIPT_PATH = ROOT / "script.js"
CURATOR_ID = "43983573"
REVIEW_ID_ALIASES = {
    "3717340": "927380",
    "3717330": "834530",
    "2988580": "638970",
    "1850570": "1190460",
}
ENDPOINT = f"https://store.steampowered.com/curator/{CURATOR_ID}/ajaxgetfilteredrecommendations/"
MONTHS = {name: number for number, name in enumerate(
    ["", "January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"]
)}


def fetch_reviews_html() -> str:
    query = urllib.parse.urlencode({
        "query": "", "start": 0, "count": 1000, "tagids": "",
        "sort": "recent", "app_types": "", "curations": "", "reset": "false",
    })
    request = urllib.request.Request(
        f"{ENDPOINT}?{query}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; ETASHI-Pocket-Sync/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.load(response)
    result = payload.get("results_html", "")
    if not result:
        raise RuntimeError("Steam 큐레이터 응답에 평가 목록이 없습니다.")
    return result


def plain_text(fragment: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def full_date(raw_date: str, previous: dict[str, str], app_id: str) -> str:
    match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)", raw_date.strip())
    if not match:
        return previous.get(app_id, dt.date.today().strftime("%Y.%m.%d"))
    day, month_name = int(match.group(1)), match.group(2)
    month = MONTHS.get(month_name)
    if not month:
        return previous.get(app_id, dt.date.today().strftime("%Y.%m.%d"))
    today = dt.date.today()
    old = previous.get(app_id, "")
    old_year = int(old[:4]) if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", old) else None
    year = old_year or today.year
    candidate = dt.date(year, month, day)
    if not old_year and candidate > today + dt.timedelta(days=31):
        candidate = candidate.replace(year=year - 1)
    return candidate.strftime("%Y.%m.%d")


def fetch_tag_names() -> dict[int, str]:
    request = urllib.request.Request(
        "https://store.steampowered.com/tagdata/populartags/koreana",
        headers={"User-Agent": "Mozilla/5.0 (compatible; ETASHI-Pocket-Sync/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return {int(item["tagid"]): str(item["name"]) for item in json.load(response)}


def parse_reviews(source: str, tag_names: dict[int, str]) -> list[dict[str, object]]:
    old_reviews: dict[str, dict[str, object]] = {}
    if JSON_PATH.exists():
        old_reviews = {str(item["id"]): item for item in json.loads(JSON_PATH.read_text(encoding="utf-8"))}
    old_dates = {app_id: str(item.get("date", "")) for app_id, item in old_reviews.items()}

    chunks = re.split(r'(?=<div\s+data-panel=.*?class="recommendation"\s*>)', source)
    reviews: list[dict[str, object]] = []
    for chunk in chunks:
        app_match = re.search(r'data-ds-appid="(\d+)"', chunk)
        image_match = re.search(r'<div class="capsule[^>]*>\s*<img src="([^"]+)" alt="([^"]*)"', chunk)
        desc_match = re.search(r'<div class="recommendation_desc">(.*?)</div>', chunk, re.S)
        date_match = re.search(r'<span class="curator_review_date">(.*?)</span>', chunk, re.S)
        if not all((app_match, image_match, desc_match)):
            continue
        app_id = app_match.group(1)
        description = plain_text(desc_match.group(1))
        score_match = re.match(r"【\s*([1-5])\s*/\s*5\s*】\s*(.*)", description)
        score = int(score_match.group(1)) if score_match else 0
        quote = score_match.group(2).strip() if score_match else description
        verdict = "비추천" if "color_not_recommended" in chunk else "추천"
        raw_date = plain_text(date_match.group(1)) if date_match else ""
        tag_match = re.search(r'data-ds-tagids="(\[[^\"]*\])"', chunk)
        tag_ids = json.loads(html_lib.unescape(tag_match.group(1))) if tag_match else []
        review = {
            "id": app_id,
            "title": html_lib.unescape(image_match.group(2)),
            "score": score,
            "verdict": verdict,
            "quote": quote,
            "date": full_date(raw_date, old_dates, app_id),
            "image": html_lib.unescape(image_match.group(1)),
            "tags": [tag_names[tag_id] for tag_id in tag_ids if tag_id in tag_names][:3],
        }
        if app_id in REVIEW_ID_ALIASES:
            review["reviewId"] = REVIEW_ID_ALIASES[app_id]
        cached_full_review = old_reviews.get(app_id, {}).get("fullReview")
        if cached_full_review:
            review["fullReview"] = cached_full_review
        reviews.append(review)
    if len(reviews) < 1:
        raise RuntimeError("Steam 평가를 하나도 해석하지 못했습니다.")
    return reviews


def fetch_full_review_once(app_id: str) -> str:
    review_id = REVIEW_ID_ALIASES.get(app_id, app_id)
    request = urllib.request.Request(
        f"https://steamcommunity.com/id/etashi04/recommended/{review_id}/",
        headers={"User-Agent": "Mozilla/5.0 (compatible; ETASHI-Pocket-Sync/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")
    match = re.search(r'<textarea[^>]*class="review_edit_text_area"[^>]*>(.*?)</textarea>', page, re.S)
    if match:
        text = html_lib.unescape(match.group(1)).replace("\r\n", "\n").strip()
    else:
        meta = re.search(r'<meta\s+(?:name="Description"|property="og:description")\s+content="([^"]*)"', page, re.I)
        if not meta:
            return ""
        text = html_lib.unescape(meta.group(1)).strip()
    text = re.sub(r"\[quote\][\s\S]*?\[/quote\]\s*$", "", text, flags=re.I).strip()
    text = re.sub(r"📮\s*평가모음집[\s\S]*$", "", text).strip()
    text = re.sub(r"\[/?b\]", "", text, flags=re.I)
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    for _ in range(min(3, len(lines))):
        if lines and (lines[0].lstrip().startswith(("■", "□", "ㅤ", "（")) or "★" in lines[0]):
            lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(line.rstrip() for line in lines).strip()


def fetch_full_review(app_id: str) -> str:
    for attempt in range(3):
        try:
            text = fetch_full_review_once(app_id)
            if text:
                return text
        except Exception:
            if attempt == 2:
                raise
        time.sleep(0.8 * (attempt + 1))
    return ""


def hydrate_full_reviews(reviews: list[dict[str, object]]) -> None:
    missing = [review for review in reviews if not review.get("fullReview")]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_full_review, str(review["id"])): review for review in missing}
        for job in as_completed(jobs):
            review = jobs[job]
            try:
                review["fullReview"] = job.result()
            except Exception as error:
                print(f"Full review fetch failed for {review['id']}: {error}")
                review["fullReview"] = ""


def write_data(reviews: list[dict[str, object]]) -> None:
    compact = json.dumps(reviews, ensure_ascii=False, separators=(",", ":"))
    pretty = json.dumps(reviews, ensure_ascii=False, indent=2) + "\n"
    JSON_PATH.write_text(pretty, encoding="utf-8")
    JS_DATA_PATH.write_text(f"window.STEAM_REVIEW_DATA={compact};\n", encoding="utf-8")

    script = SCRIPT_PATH.read_text(encoding="utf-8")
    replacement = f"const fallbackSteamReviews = {pretty.rstrip()};"
    updated, count = re.subn(
        r"const fallbackSteamReviews = \[[\s\S]*?\]\s*;",
        lambda _: replacement,
        script,
        count=1,
    )
    if count != 1:
        raise RuntimeError("script.js의 평가 데이터 영역을 찾지 못했습니다.")
    SCRIPT_PATH.write_text(updated, encoding="utf-8")


def main() -> None:
    reviews = parse_reviews(fetch_reviews_html(), fetch_tag_names())
    hydrate_full_reviews(reviews)
    write_data(reviews)
    print(f"Steam curator reviews synchronized: {len(reviews)}")


if __name__ == "__main__":
    main()
