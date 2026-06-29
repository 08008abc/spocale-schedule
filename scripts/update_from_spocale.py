#!/usr/bin/env python3
"""
スポカレ予定更新スクリプト

GitHub Actionsで毎日0時（日本時間）に実行し、
data/schedule.json を「実行日当日＋翌日」の2日分に更新します。

ルール:
- team_and_players ページは個別試合として取得
- sports / leagues ページは大会・イベントとして取得
- 取得結果が0件の場合は、空データで上書きせず既存データを維持
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


def now_jst() -> datetime:
    return datetime.now(JST)


def target_dates() -> set[str]:
    now = now_jst()
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
        "generated_at": now_jst().isoformat(),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "events": [],
    }


def fetch(url: str) -> str:
    response = requests.get(
        url,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; spocale-daily-schedule/1.0)",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        },
    )
    response.raise_for_status()
    return response.text


def cleanup(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def page_name(soup: BeautifulSoup) -> str:
    for tag in ("h1", "h2"):
        node = soup.find(tag)
        if node:
            text = cleanup(node.get_text(" ", strip=True))
            if text:
                return text.replace(" | スポカレ", "")
    title = soup.find("title")
    if title:
        return cleanup(title.get_text(" ", strip=True)).replace(" | スポカレ", "")
    return "スポカレ予定"


def is_team_page(url: str) -> bool:
    return "/team_and_players/" in url


def normalize_sport(name: str, url: str) -> str:
    text = cleanup(name)
    # URLから分かりやすい競技名に補正できるもの
    sports_id_map = {
        "/sports/1/": "野球",
        "/sports/2/": "サッカー",
        "/sports/3/": "ラグビー",
        "/sports/5/": "バスケットボール",
        "/sports/6/": "ゴルフ",
        "/sports/7": "陸上競技",
        "/sports/8/": "テニス",
        "/sports/9": "競馬",
        "/sports/14/": "バレーボール",
        "/sports/18/": "バドミントン",
        "/sports/22": "競艇",
        "/sports/32": "卓球",
        "/sports/43/": "アメリカンフットボール",
        "/sports/44/": "フィギュアスケート",
        "/sports/50": "スケートボード",
        "/sports/51/": "BMX",
        "/sports/52": "スポーツクライミング",
    }
    for key, sport in sports_id_map.items():
        if key in url:
            return sport
    # ページタイトル由来の補正
    if "野球" in text or "カブス" in text or "MLB" in text:
        return "野球"
    if "サッカー" in text or "日本代表" in text or "INAC" in text:
        return "サッカー"
    if "バレー" in text or "ヴィクトリーナ" in text:
        return "バレーボール"
    if "ラグビー" in text or "スティーラーズ" in text:
        return "ラグビー"
    if "ゴルフ" in text:
        return "ゴルフ"
    if "陸上" in text or "マラソン" in text:
        return "陸上競技"
    if "バドミントン" in text:
        return "バドミントン"
    return text.replace("の日程一覧", "")


def guess_venue(line: str) -> str:
    # スポカレの行から会場らしい括弧や単語を拾う簡易処理
    patterns = [
        r"会場[:：]\s*([^|／]+)",
        r"開催地[:：]\s*([^|／]+)",
        r"@([^|／]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return cleanup(match.group(1))
    return "記載なし"


def guess_tv(line: str) -> str:
    tv_words = ["NHK", "BS", "地上波", "フジテレビ", "日本テレビ", "TBS", "テレビ朝日", "テレビ東京", "WOWOW", "J SPORTS", "ゴルフネットワーク"]
    found = [word for word in tv_words if word in line]
    return "、".join(dict.fromkeys(found)) if found else "記載なし"


def guess_stream(line: str) -> str:
    stream_words = ["YouTubeLive", "YouTube", "U-NEXT", "DAZN", "ABEMA", "Lemino", "SPOTV NOW", "MLB.TV", "Amazon Prime Video", "VOLLEYBALL TV", "J SPORTSオンデマンド"]
    found = [word for word in stream_words if word in line]
    return "、".join(dict.fromkeys(found)) if found else "記載なし"


def split_target_from_line(line: str, time: str) -> str:
    text = cleanup(line)
    if time != "記載なし":
        text = cleanup(text.replace(time, " ", 1))
    text = re.sub(r"^[-–—\s]+", "", text)
    return text or "記載なし"


def parse_page(url: str, html: str, dates: set[str]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    name = page_name(soup)
    sport = normalize_sport(name, url)
    text = soup.get_text("\n", strip=True)

    # 例: 2026.06.29[月] のような表記を探す
    date_re = re.compile(r"(20\d{2})\.(\d{2})\.(\d{2})\[[^\]]+\]")
    matches = list(date_re.finditer(text))
    results: list[dict[str, Any]] = []

    for i, match in enumerate(matches):
        iso = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        if iso not in dates:
            continue

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        lines = [cleanup(x) for x in block.splitlines() if cleanup(x)]

        # 時刻を含む行だけ候補にする
        candidate_lines = [line for line in lines if re.search(r"\d{1,2}:\d{2}|終日", line)]

        # ページによっては日付直下に時刻がなく、周辺行が分かれるため近い行を連結
        if not candidate_lines and lines:
            joined = " ".join(lines[:8])
            if re.search(r"\d{1,2}:\d{2}|終日", joined):
                candidate_lines = [joined]

        for line in candidate_lines:
            time_match = re.search(r"(\d{1,2}:\d{2}|終日)", line)
            time = time_match.group(1) if time_match else "記載なし"

            if is_team_page(url):
                item_type = "試合"
                target = split_target_from_line(line, time)
                event_name = name
            else:
                item_type = "大会"
                target = "大会のみ"
                event_name = split_target_from_line(line, time)

            results.append({
                "date": iso,
                "time": time,
                "type": item_type,
                "sport": sport,
                "event": cleanup(event_name),
                "target": cleanup(target),
                "venue": guess_venue(line),
                "tv": guess_tv(line),
                "stream": guess_stream(line),
                "source": url,
            })

    return results


def dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for e in events:
        key = (
            e.get("date", ""),
            e.get("time", ""),
            e.get("type", ""),
            e.get("sport", ""),
            e.get("event", ""),
            e.get("target", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return sorted(unique, key=lambda x: (x.get("date", ""), x.get("time", "99:99"), x.get("sport", "")))


def main() -> None:
    dates = target_dates()
    events: list[dict[str, Any]] = []
    errors: list[str] = []

    for url in SOURCE_URLS:
        try:
            html = fetch(url)
            events.extend(parse_page(url, html, dates))
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    events = dedupe(events)
    existing = load_existing()

    if not events:
        existing["generated_at"] = now_jst().isoformat()
        existing["timezone"] = "Asia/Tokyo"
        existing["source_name"] = "スポカレ"
        existing["source_urls"] = SOURCE_URLS
        existing["last_update_note"] = "新規取得が0件だったため、既存データを維持しました。ページ側は日本時間の当日＋翌日だけを表示します。"
        existing["last_update_errors"] = errors[:30]
        OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print("No events fetched. Existing data preserved.")
        return

    payload = {
        "generated_at": now_jst().isoformat(),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "display_rule": "毎日0時に日本時間の実行日当日と翌日の2日分へ更新",
        "events": events,
        "last_update_errors": errors[:30],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated {len(events)} events for {', '.join(sorted(dates))}.")


if __name__ == "__main__":
    main()
