#!/usr/bin/env python3
"""
スポカレ予定更新スクリプト。

大事な安全装置:
- 取得結果が0件だった場合、既存の data/schedule.json を空で上書きしません。
  これにより、ページが突然0件表示になる事故を防ぎます。

注意:
- スポカレ側のHTML構造やアクセス制限により、取得ロジックは調整が必要になる場合があります。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "schedule.json"

SOURCE_URLS = [
    "https://spocale.com/sports/14/team_and_players/871",
    "https://spocale.com/sports/2/team_and_players/1315",
    "https://spocale.com/sports/3/team_and_players/258",
    "https://spocale.com/sports/2/team_and_players/53",
    "https://spocale.com/sports/2/team_and_players/2596",
    "https://spocale.com/sports/1/team_and_players/92",
    "https://spocale.com/sports/1/team_and_players/3418",
    "https://spocale.com/sports/1/team_and_players/7731",
    "https://spocale.com/sports/1/team_and_players/7776",
    "https://spocale.com/sports/1/team_and_players/2280",
    "https://spocale.com/sports/1/team_and_players/2279",
    "https://spocale.com/sports/2/team_and_players/3815",
    "https://spocale.com/sports/14/team_and_players/4829",
    "https://spocale.com/sports/14/team_and_players/3588",
    "https://spocale.com/sports/2/team_and_players/269",
    "https://spocale.com/sports/2/team_and_players/437",
    "https://spocale.com/sports/2/team_and_players/2615",
    "https://spocale.com/sports/5/team_and_players/519",
    "https://spocale.com/sports/5/team_and_players/3013",
    "https://spocale.com/sports/3/team_and_players/3684",
    "https://spocale.com/sports/3/team_and_players/22376",
    "https://spocale.com/sports/1/team_and_players/1316",
    "https://spocale.com/sports/43/team_and_players/1216",
    "https://spocale.com/sports/9",
    "https://spocale.com/sports/22",
    "https://spocale.com/sports/11/leagues/75",
    "https://spocale.com/sports/7",
    "https://spocale.com/sports/18/leagues/556",
    "https://spocale.com/sports/32",
    "https://spocale.com/sports/6/leagues/310",
    "https://spocale.com/sports/50",
    "https://spocale.com/sports/52",
    "https://spocale.com/sports/51/leagues/697",
    "https://spocale.com/sports/44/leagues/577",
    "https://spocale.com/sports/8/leagues/130",
    "https://spocale.com/sports/8/leagues/806",
    "https://spocale.com/sports/8/leagues/232",
    "https://spocale.com/sports/8/leagues/807",
    "https://spocale.com/sports/2/team_and_players/335",
    "https://spocale.com/sports/2/team_and_players/22",
    "https://spocale.com/sports/5/team_and_players/121",
]


def target_dates() -> set[str]:
    now = datetime.now(JST)
    return {
        now.strftime("%Y-%m-%d"),
        (now + timedelta(days=1)).strftime("%Y-%m-%d"),
    }


def load_existing() -> dict[str, Any]:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "generated_at": datetime.now(JST).isoformat(),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "events": [],
    }


def fetch(url: str) -> str:
    res = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; spocale-schedule-bot/1.0)",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        },
    )
    res.raise_for_status()
    return res.text


def page_name(soup: BeautifulSoup) -> str:
    for tag in ["h1", "h2"]:
        node = soup.find(tag)
        if node:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    title = soup.find("title")
    if title:
        return title.get_text(" ", strip=True).replace(" | スポカレ", "")
    return "スポカレ予定"


def is_team_page(url: str) -> bool:
    return "/team_and_players/" in url


def norm_date(y: str, m: str, d: str) -> str:
    return f"{y}-{m}-{d}"


def cleanup(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_page(url: str, html: str, dates: set[str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    name = page_name(soup)
    text = soup.get_text("\n", strip=True)

    date_re = re.compile(r"(20\d{2})\.(\d{2})\.(\d{2})\[[^\]]+\]")
    matches = list(date_re.finditer(text))
    results: list[dict[str, Any]] = []

    for i, m in enumerate(matches):
        iso = norm_date(m.group(1), m.group(2), m.group(3))
        if iso not in dates:
            continue

        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        # スポカレの一覧はリンクテキストが1行にまとまることが多い
        lines = [cleanup(x) for x in block.splitlines() if cleanup(x)]
        candidate_lines = [x for x in lines if re.search(r"\d{1,2}:\d{2}|終日", x)]

        for line in candidate_lines:
            time_match = re.search(r"(\d{1,2}:\d{2}|終日)", line)
            time = time_match.group(1) if time_match else "記載なし"

            if is_team_page(url):
                item_type = "試合"
                target = line
                event_name = name
            else:
                item_type = "大会"
                target = "大会のみ"
                event_name = line

            results.append({
                "date": iso,
                "time": time,
                "type": item_type,
                "sport": name,
                "event": event_name,
                "target": target,
                "venue": "記載なし",
                "tv": "記載なし",
                "stream": "記載なし",
                "source": url,
            })

    return results


def dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for e in events:
        key = (
            e.get("date"),
            e.get("time"),
            e.get("type"),
            e.get("sport"),
            e.get("event"),
            e.get("target"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def main() -> None:
    dates = target_dates()
    events: list[dict[str, Any]] = []
    errors: list[str] = []

    for url in SOURCE_URLS:
        try:
            events.extend(parse_page(url, fetch(url), dates))
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    events = dedupe(events)

    existing = load_existing()

    if not events:
        # 0件で上書きしない。既存データを維持し、エラー情報だけ追記。
        existing["generated_at"] = datetime.now(JST).isoformat()
        existing["last_update_note"] = "新規取得が0件だったため、既存の予定データを維持しました。"
        existing["last_update_errors"] = errors[:20]
        OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print("No events fetched. Existing schedule preserved.")
        return

    payload = {
        "generated_at": datetime.now(JST).isoformat(),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "events": events,
        "last_update_errors": errors[:20],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated {len(events)} events.")


if __name__ == "__main__":
    main()
