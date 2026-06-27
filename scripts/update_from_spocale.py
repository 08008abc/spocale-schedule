#!/usr/bin/env python3
"""
スポカレ対象URLから data/schedule.json を更新するための雛形です。

注意:
- スポカレ側のHTML構造変更に弱いので、運用時は定期的に確認してください。
- 競技ページ・リーグページは「個別試合ではなく大会・イベント名のみ」を出す想定です。
- 放送・配信詳細は試合詳細ページ側にある場合があるため、必要に応じて詳細ページ取得を追加してください。
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


def today_and_tomorrow() -> set[str]:
    now = datetime.now(JST)
    return {
        now.strftime("%Y-%m-%d"),
        (now + timedelta(days=1)).strftime("%Y-%m-%d"),
    }


def get_text(url: str) -> str:
    res = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 schedule-page-updater/1.0"},
    )
    res.raise_for_status()
    return res.text


def is_team_page(url: str) -> bool:
    return "/team_and_players/" in url


def parse_spocale_page(url: str, html: str, target_dates: set[str]) -> list[dict[str, Any]]:
    """
    汎用パーサーの雛形です。
    スポカレのページには日付見出しと試合リンクが並ぶため、
    まずテキストから該当日付付近を抽出する方針にしています。

    本格運用では、詳細ページのリンクをたどってテレビ・ネット配信欄を取得してください。
    """
    soup = BeautifulSoup(html, "html.parser")
    page_title = soup.find(["h1", "h2"])
    page_name = page_title.get_text(" ", strip=True) if page_title else "スポカレ予定"

    text = soup.get_text("\n", strip=True)
    events: list[dict[str, Any]] = []

    # 例: 2026.06.28[日] のような日付見出しを yyyy-mm-dd に変換
    date_re = re.compile(r"(20\d{2})\.(\d{2})\.(\d{2})\[[^\]]+\]")
    matches = list(date_re.finditer(text))

    for i, m in enumerate(matches):
        iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if iso not in target_dates:
            continue

        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        # 個別チームページは試合単位、競技/リーグページは大会名単位で扱う
        if is_team_page(url):
            # 時刻を含む行をざっくり抽出
            for line in block.splitlines():
                if not re.search(r"\d{1,2}:\d{2}", line):
                    continue
                line = re.sub(r"\s+", " ", line).strip()
                if len(line) < 6:
                    continue
                time_match = re.search(r"(\d{1,2}:\d{2})", line)
                events.append({
                    "date": iso,
                    "time": time_match.group(1) if time_match else "記載なし",
                    "type": "試合",
                    "sport": "記載なし",
                    "event": page_name,
                    "target": line,
                    "venue": "記載なし",
                    "tv": "記載なし",
                    "stream": "記載なし",
                    "source": url,
                })
        else:
            # 大会/イベント名として、時刻を含む行を1予定として扱う
            for line in block.splitlines():
                if not re.search(r"\d{1,2}:\d{2}|終日", line):
                    continue
                line = re.sub(r"\s+", " ", line).strip()
                time_match = re.search(r"(\d{1,2}:\d{2}|終日)", line)
                events.append({
                    "date": iso,
                    "time": time_match.group(1) if time_match else "記載なし",
                    "type": "大会",
                    "sport": page_name,
                    "event": line,
                    "target": "大会のみ",
                    "venue": "記載なし",
                    "tv": "記載なし",
                    "stream": "記載なし",
                    "source": url,
                })

    return events


def dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for e in events:
        key = (e["date"], e["time"], e["sport"], e["event"], e["target"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def main() -> None:
    target_dates = today_and_tomorrow()
    all_events: list[dict[str, Any]] = []

    for url in SOURCE_URLS:
        try:
            html = get_text(url)
            all_events.extend(parse_spocale_page(url, html, target_dates))
        except Exception as exc:
            print(f"warning: failed to fetch {url}: {exc}")

    payload = {
        "generated_at": datetime.now(JST).isoformat(),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "events": dedupe(all_events),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
