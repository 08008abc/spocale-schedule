#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スポカレ自動更新 安全版

- 日本時間の今日・明日を毎回自動計算
- team_and_players は個別試合として取得
- sports / leagues は大会として取得
- 予定が0件だった場合、既存の data/schedule.json を空で上書きしない
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "schedule.json"
JST = ZoneInfo("Asia/Tokyo")

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}

SPORT_WORDS = [
    "野球", "サッカー", "バレーボール", "バスケットボール", "ラグビー", "テニス",
    "ゴルフ", "陸上競技", "バドミントン", "卓球", "競泳", "フィギュアスケート",
    "ハンドボール", "柔道", "ボクシング", "格闘技", "モータースポーツ", "体操",
    "プロレス", "相撲", "トライアスロン", "ソフトボール", "アイスホッケー", "ホッケー"
]

KNOWN_LEAGUES = [
    "メジャーリーグ(MLB)", "MLB",
    "FIVBバレーボールネーションズリーグ", "ネーションズリーグ",
    "プレナスなでしこリーグ1部", "なでしこリーグ",
    "WEリーグ", "J1リーグ", "J2リーグ", "J3リーグ",
    "リーグワン", "ジャパンラグビー リーグワン",
    "BWFワールドツアー", "JLPGAツアー", "PGAツアー", "ダイヤモンドリーグ",
]

DATE_CAPTURE_RE = re.compile(r"(20\d{2})\.(\d{2})\.(\d{2})\[[^\]]+\]")
TIME_RE = re.compile(r"^(\d{1,2}:\d{2}|終日)\s+")
REPEATED_TIME_AFTER_VS_RE = re.compile(r"\b(VS|vs|Vs)\s+\d{1,2}:\d{2}\b")


@dataclass
class Event:
    date: str
    time: str
    type: str
    sport: str
    event: str
    target: str
    venue: str
    tv: str
    stream: str
    source: str

    def key(self):
        return (self.date, self.time, normalize(self.sport), normalize(self.event), normalize(self.target))

    def as_dict(self):
        return {
            "date": self.date,
            "time": self.time or "記載なし",
            "type": self.type or "記載なし",
            "sport": self.sport or "記載なし",
            "event": self.event or "記載なし",
            "target": self.target or "記載なし",
            "venue": self.venue or "記載なし",
            "tv": self.tv or "記載なし",
            "stream": self.stream or "記載なし",
            "source": self.source,
        }


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("　", " ")).strip()


def today_tomorrow() -> set[str]:
    today = datetime.now(JST).date()
    return {today.isoformat(), (today + timedelta(days=1)).isoformat()}


def iso_from_spocale_date(value: str) -> str | None:
    m = DATE_CAPTURE_RE.search(value)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{mo}-{d}"


def page_title(soup: BeautifulSoup) -> str:
    h2 = soup.find("h2")
    if h2:
        text = normalize(h2.get_text(" ", strip=True))
        if text:
            return text
    title = soup.find("title")
    if title:
        return normalize(title.get_text(" ", strip=True)).replace("の日程一覧 | スポカレ", "")
    return "記載なし"


def detect_sport(text: str) -> str:
    for sport in SPORT_WORDS:
        if sport in text:
            return sport
    return "記載なし"


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def split_event_line(line: str):
    line = normalize(line)
    m = TIME_RE.match(line)
    if not m:
        return "記載なし", "記載なし", line

    time_text = m.group(1)
    rest = normalize(line[m.end():])

    sport = "記載なし"
    for word in SPORT_WORDS:
        if rest.startswith(word + " "):
            sport = word
            rest = normalize(rest[len(word):])
            break

    return time_text, sport, rest


def find_league(text: str) -> str:
    for league in KNOWN_LEAGUES:
        if league in text:
            return league
    return "記載なし"


def remove_duplicate_tail(text: str) -> str:
    words = normalize(text).split()
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half])
    if len(words) >= 2 and words[-1] == words[-2]:
        return " ".join(words[:-1])
    return normalize(text)


def collect_date_event_pairs(soup: BeautifulSoup, wanted_dates: set[str]) -> list[tuple[str, str]]:
    lines = [normalize(x) for x in soup.get_text("\n", strip=True).splitlines()]
    rows: list[tuple[str, str]] = []
    current_date: str | None = None
    seen: set[tuple[str, str]] = set()

    for line in lines:
        if not line:
            continue

        maybe_date = iso_from_spocale_date(line)
        if maybe_date:
            current_date = maybe_date
            continue

        if current_date in wanted_dates and TIME_RE.match(line):
            key = (current_date, line)
            if key not in seen:
                seen.add(key)
                rows.append(key)

    return rows


def parse_team_event(date: str, line: str, url: str) -> Event:
    time_text, sport, rest = split_event_line(line)
    rest = REPEATED_TIME_AFTER_VS_RE.sub(r"\1", rest)
    rest = normalize(rest)

    league = find_league(rest)
    target = rest
    venue = "記載なし"

    if league != "記載なし" and league in rest:
        before, after = rest.split(league, 1)
        target = normalize(before)
        venue = remove_duplicate_tail(after)

    target = target.replace(" VS ", " vs ").replace("VS", "vs").replace("Vs", "vs")

    return Event(date, time_text, "試合", sport, league, target or "記載なし", venue or "記載なし", "記載なし", "記載なし", url)


def parse_page_event(date: str, line: str, url: str, title: str, page_sport: str) -> Event:
    time_text, sport, rest = split_event_line(line)
    if sport == "記載なし":
        sport = page_sport

    event_name = normalize(rest)
    if "|" in event_name:
        event_name = normalize(event_name.split("|", 1)[0])

    if title and title != "記載なし" and title not in event_name:
        event_name = normalize(f"{title} {event_name}")

    venue = "記載なし"
    parts = rest.split()
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        venue = parts[-1]

    return Event(date, time_text, "大会", sport, event_name or title or "記載なし", "大会のみ", venue, "記載なし", "記載なし", url)


def parse_url(url: str, html: str, wanted_dates: set[str]) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    title = page_title(soup)
    page_sport = detect_sport(f"{title} {soup.get_text(' ', strip=True)[:3000]}")
    is_team_page = "/team_and_players/" in url

    events: list[Event] = []
    for date, line in collect_date_event_pairs(soup, wanted_dates):
        try:
            if is_team_page:
                events.append(parse_team_event(date, line, url))
            else:
                events.append(parse_page_event(date, line, url, title, page_sport))
        except Exception:
            continue

    return events


def dedupe(events: list[Event]) -> list[Event]:
    by_key: dict[tuple, Event] = {}
    for event in events:
        key = event.key()
        if key not in by_key:
            by_key[key] = event
        else:
            old = by_key[key]
            if old.venue == "記載なし" and event.venue != "記載なし":
                old.venue = event.venue

    def sort_key(event: Event):
        if event.time == "終日":
            minutes = 9999
        else:
            m = re.match(r"^(\d{1,2}):(\d{2})", event.time)
            minutes = int(m.group(1)) * 60 + int(m.group(2)) if m else 9998
        return (event.date, minutes, event.sport, event.event, event.target)

    return sorted(by_key.values(), key=sort_key)


def load_existing() -> dict:
    if not DATA_PATH.exists():
        return {}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_payload(payload: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    wanted_dates = today_tomorrow()
    all_events: list[Event] = []
    errors: list[str] = []
    fetched_pages = 0
    parsed_pages = 0

    for url in SOURCE_URLS:
        try:
            html = fetch_html(url)
            fetched_pages += 1
            events = parse_url(url, html, wanted_dates)
            if events:
                parsed_pages += 1
                all_events.extend(events)
            time.sleep(0.25)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    events = dedupe(all_events)
    now = datetime.now(JST)

    if not events:
        existing = load_existing()
        existing["generated_at"] = now.isoformat(timespec="seconds")
        existing["timezone"] = "Asia/Tokyo"
        existing["source_name"] = "スポカレ"
        existing["source_urls"] = SOURCE_URLS
        existing["target_dates"] = sorted(wanted_dates)
        existing["last_update_note"] = (
            "新規取得が0件だったため、既存の予定データを維持しました。"
            f" 取得成功ページ数: {fetched_pages}, 予定検出ページ数: {parsed_pages}, 予定数: 0"
        )
        existing["last_update_errors"] = errors[:30]
        existing.setdefault("events", [])
        save_payload(existing)
        print("events=0; kept existing events")
    else:
        payload = {
            "generated_at": now.isoformat(timespec="seconds"),
            "timezone": "Asia/Tokyo",
            "source_name": "スポカレ",
            "source_urls": SOURCE_URLS,
            "target_dates": sorted(wanted_dates),
            "events": [event.as_dict() for event in events],
            "last_update_note": (
                "日本時間の今日・明日分を自動取得しました。"
                f" 取得成功ページ数: {fetched_pages}, 予定検出ページ数: {parsed_pages}, 予定数: {len(events)}"
            ),
            "last_update_errors": errors[:30],
        }
        save_payload(payload)
        print(f"events={len(events)}")

    print(f"target_dates={sorted(wanted_dates)}")
    print(f"fetched_pages={fetched_pages}/{len(SOURCE_URLS)}")
    print(f"parsed_pages={parsed_pages}")
    if errors:
        print("errors:")
        for err in errors[:10]:
            print("-", err)

    return 0 if fetched_pages > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
