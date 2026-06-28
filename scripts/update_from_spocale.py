#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スポカレから日本時間の「今日・明日」の予定を取得して data/schedule.json を更新します。

- team_and_players: 個別試合として取得
- sports / leagues: 大会・イベントとして取得
- 重複予定は統合
- 取得エラーは last_update_errors に保存
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
from bs4 import BeautifulSoup, Tag


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

DATE_RE = re.compile(r"^(20\d{2})\.(\d{2})\.(\d{2})\[[^\]]+\]$")
TIME_RE = re.compile(r"^(\d{1,2}:\d{2}|終日)\s+")
REPEATED_TIME_AFTER_VS_RE = re.compile(r"\b(VS|vs|Vs)\s+\d{1,2}:\d{2}\b")

SPORT_WORDS = [
    "野球", "サッカー", "バレーボール", "バスケットボール", "ラグビー", "テニス", "ゴルフ",
    "陸上競技", "バドミントン", "卓球", "競泳", "フィギュアスケート", "ハンドボール",
    "柔道", "ボクシング", "格闘技", "モータースポーツ", "体操", "プロレス", "相撲",
    "トライアスロン", "ソフトボール", "アイスホッケー", "ホッケー"
]

KNOWN_LEAGUES = [
    "メジャーリーグ(MLB)", "MLB",
    "FIVBバレーボールネーションズリーグ", "ネーションズリーグ",
    "Vリーグ", "SVリーグ",
    "プレナスなでしこリーグ1部", "プレナスなでしこリーグ2部", "なでしこリーグ",
    "WEリーグ", "J1リーグ", "J2リーグ", "J3リーグ", "天皇杯", "ルヴァンカップ",
    "リーグワン", "ジャパンラグビー リーグワン",
    "Bリーグ", "Wリーグ",
    "BWFワールドツアー",
    "JLPGAツアー", "PGAツアー",
    "ダイヤモンドリーグ",
]


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
        return (self.date, self.time, norm(self.sport), norm(self.event), norm(self.target))

    def as_dict(self):
        return {
            "date": self.date,
            "time": self.time,
            "type": self.type,
            "sport": self.sport or "記載なし",
            "event": self.event or "記載なし",
            "target": self.target or "記載なし",
            "venue": self.venue or "記載なし",
            "tv": self.tv or "記載なし",
            "stream": self.stream or "記載なし",
            "source": self.source,
        }


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").replace("　", " ")).strip()


def get_target_dates():
    today = datetime.now(JST).date()
    return {today.isoformat(), (today + timedelta(days=1)).isoformat()}


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def page_title(soup):
    h2 = soup.find("h2")
    if h2:
        t = norm(h2.get_text(" ", strip=True))
        if t:
            return t
    title = soup.find("title")
    if title:
        return norm(title.get_text(" ", strip=True)).replace("の日程一覧 | スポカレ", "")
    return "記載なし"


def detect_sport(text):
    text = norm(text)
    for word in SPORT_WORDS:
        if word in text:
            return word
    return "記載なし"


def line_to_date(line):
    m = DATE_RE.match(norm(line))
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{mo}-{d}"


def is_event_text(text):
    text = norm(text)
    if not text or text in {"チーム一覧", "大会・リーグ一覧", "絞込み検索", "絞込み"}:
        return False
    if DATE_RE.match(text):
        return False
    return bool(TIME_RE.match(text))


def collect_rows(soup, target_dates):
    body = soup.body or soup
    current_date = None
    rows = []
    seen = set()

    for node in body.descendants:
        if not isinstance(node, Tag):
            continue
        if node.name in {"script", "style", "noscript"}:
            continue

        text = norm(node.get_text(" ", strip=True))
        iso = line_to_date(text)
        if iso:
            current_date = iso
            continue

        if node.name == "a" and current_date in target_dates and is_event_text(text):
            key = (current_date, text)
            if key not in seen:
                seen.add(key)
                rows.append(key)

    current_date = None
    for raw in soup.get_text("\n", strip=True).splitlines():
        line = norm(raw)
        iso = line_to_date(line)
        if iso:
            current_date = iso
            continue

        if current_date in target_dates and is_event_text(line):
            key = (current_date, line)
            if key not in seen:
                seen.add(key)
                rows.append(key)

    return rows


def split_event_line(line):
    line = norm(line)
    m = TIME_RE.match(line)
    if not m:
        return "記載なし", "記載なし", line

    start_time = m.group(1)
    rest = norm(line[m.end():])

    sport = "記載なし"
    for word in SPORT_WORDS:
        if rest.startswith(word + " "):
            sport = word
            rest = norm(rest[len(word):])
            break
        if rest == word:
            sport = word
            rest = ""
            break

    return start_time, sport, rest


def find_league(text, fallback=""):
    for league in KNOWN_LEAGUES:
        if league in text:
            return league
    return fallback if fallback else "記載なし"


def compact_duplicate_tail(text):
    words = norm(text).split()
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half])
    if len(words) >= 2 and words[-1] == words[-2]:
        return " ".join(words[:-1])
    return norm(text)


def parse_team_event(date, line, url, title):
    start_time, sport, rest = split_event_line(line)
    rest = REPEATED_TIME_AFTER_VS_RE.sub(r"\1", rest)
    rest = norm(rest)

    league = find_league(rest, "")
    target = rest
    venue = "記載なし"

    if league != "記載なし" and league in rest:
        before, after = rest.split(league, 1)
        target = norm(before)
        venue = compact_duplicate_tail(after)

    target = target.replace(" VS ", " vs ").replace("VS", "vs").replace("Vs", "vs")

    return Event(date, start_time, "試合", sport, league, target or "記載なし", venue or "記載なし", "記載なし", "記載なし", url)


def parse_non_team_event(date, line, url, title, page_sport):
    start_time, line_sport, rest = split_event_line(line)
    sport = line_sport if line_sport != "記載なし" else page_sport

    event_name = norm(rest)
    if "|" in event_name:
        event_name = norm(event_name.split("|", 1)[0])
    if title and title != "記載なし" and title not in event_name:
        event_name = norm(f"{title} {event_name}")

    venue = "記載なし"
    parts = rest.split()
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        venue = parts[-1]

    return Event(date, start_time, "大会", sport, event_name or title or "記載なし", "大会のみ", venue, "記載なし", "記載なし", url)


def parse_page(url, html, target_dates):
    soup = BeautifulSoup(html, "html.parser")
    title = page_title(soup)
    page_sport = detect_sport(f"{title} {soup.get_text(' ', strip=True)[:2000]}")
    is_team = "/team_and_players/" in url

    events = []
    for date, line in collect_rows(soup, target_dates):
        try:
            if is_team:
                events.append(parse_team_event(date, line, url, title))
            else:
                events.append(parse_non_team_event(date, line, url, title, page_sport))
        except Exception:
            continue

    return events


def dedupe(events):
    by_key = {}
    for e in events:
        if e.key() not in by_key:
            by_key[e.key()] = e
        else:
            old = by_key[e.key()]
            if old.venue == "記載なし" and e.venue != "記載なし":
                old.venue = e.venue

    def sort_key(e):
        if e.time == "終日":
            minutes = 9999
        else:
            m = re.match(r"^(\d{1,2}):(\d{2})", e.time)
            minutes = int(m.group(1)) * 60 + int(m.group(2)) if m else 9998
        return (e.date, minutes, e.sport, e.event)

    return sorted(by_key.values(), key=sort_key)


def write_schedule(events, errors, fetched_pages, parsed_pages):
    now = datetime.now(JST)
    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "target_dates": sorted(get_target_dates()),
        "events": [e.as_dict() for e in events],
        "last_update_note": (
            f"日本時間の今日・明日分を自動取得しました。"
            f"取得成功ページ数: {fetched_pages}, 予定検出ページ数: {parsed_pages}, 予定数: {len(events)}"
        ),
        "last_update_errors": errors[:30],
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    dates = get_target_dates()
    all_events = []
    errors = []
    fetched_pages = 0
    parsed_pages = 0

    for url in SOURCE_URLS:
        try:
            html = fetch_html(url)
            fetched_pages += 1
            events = parse_page(url, html, dates)
            if events:
                parsed_pages += 1
                all_events.extend(events)
            time.sleep(0.25)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    events = dedupe(all_events)
    write_schedule(events, errors, fetched_pages, parsed_pages)

    print(f"target_dates={sorted(dates)}")
    print(f"fetched_pages={fetched_pages}/{len(SOURCE_URLS)}")
    print(f"parsed_pages={parsed_pages}")
    print(f"events={len(events)}")
    if errors:
        print("errors:")
        for e in errors[:10]:
            print("-", e)

    return 0 if fetched_pages > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
