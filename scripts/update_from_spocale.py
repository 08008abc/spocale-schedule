#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
スポカレ自動更新: 日付ブロック解析強化版

前回版で「取得成功ページ数: 41」なのに「予定検出ページ数: 0」になるケースに対応。
通常の行単位解析に加えて、ページ全文から
「2026.06.30[火] ～ 次の日付」単位のブロックを切り出して予定を探します。

出力:
  data/schedule.json
"""

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
    "User-Agent": "Mozilla/5.0 (compatible; spocale-schedule-bot/1.0)",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SPORTS = [
    "バレーボール", "バスケットボール", "バドミントン", "フィギュアスケート",
    "サッカー", "ラグビー", "テニス", "ゴルフ", "陸上競技", "野球",
    "卓球", "競泳", "相撲", "柔道", "ボクシング", "格闘技", "体操",
]

LEAGUES = [
    "メジャーリーグ(MLB)", "MLB",
    "BWFワールドツアー", "JLPGAツアー", "PGAツアー",
    "FIVBバレーボールネーションズリーグ", "ネーションズリーグ",
    "プレナスなでしこリーグ1部", "プレナスなでしこリーグ2部", "なでしこリーグ",
    "WEリーグ", "J1リーグ", "J2リーグ", "J3リーグ",
    "リーグワン", "ジャパンラグビー リーグワン",
    "ダイヤモンドリーグ",
]

DATE_RE = re.compile(r"(20\d{2})\.(\d{2})\.(\d{2})\[[^\]]+\]")
TIME_RE = re.compile(r"(\d{1,2}:\d{2}|終日|未定)\s+")
EVENT_START_RE = re.compile(r"(?=(?:\d{1,2}:\d{2}|終日|未定)\s+(?:" + "|".join(map(re.escape, SPORTS)) + r")\s+)")

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

def norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace("　", " ")).strip()

def today_tomorrow():
    today = datetime.now(JST).date()
    return {today.isoformat(), (today + timedelta(days=1)).isoformat()}

def iso_date(text):
    m = DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{mo}-{d}"

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def title_of(soup):
    h2 = soup.find("h2")
    if h2 and norm(h2.get_text(" ", strip=True)):
        return norm(h2.get_text(" ", strip=True))
    title = soup.find("title")
    if title:
        return norm(title.get_text(" ", strip=True)).replace("の日程一覧 | スポカレ", "")
    return "記載なし"

def find_sport(text):
    for s in SPORTS:
        if s in text:
            return s
    return "記載なし"

def find_league(text):
    for l in LEAGUES:
        if l in text:
            return l
    return "記載なし"

def split_line(line):
    line = norm(line)
    m = re.match(r"^(\d{1,2}:\d{2}|終日|未定)\s+", line)
    if not m:
        return "記載なし", "記載なし", line
    t = m.group(1)
    rest = norm(line[m.end():])
    sport = find_sport(rest)
    if sport != "記載なし" and rest.startswith(sport):
        rest = norm(rest[len(sport):])
    return t, sport, rest

def dedupe_tail(text):
    words = norm(text).split()
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half])
    if len(words) >= 2 and words[-1] == words[-2]:
        return " ".join(words[:-1])
    return norm(text) or "記載なし"

def parse_team(date, line, url):
    t, sport, rest = split_line(line)
    rest = re.sub(r"\b(VS|Vs|vs)\s+\d{1,2}:\d{2}\b", "vs", rest)
    rest = norm(rest.replace(" VS ", " vs ").replace("VS", "vs").replace("Vs", "vs"))

    league = find_league(rest)
    target = rest
    venue = "記載なし"

    if league != "記載なし" and league in rest:
        target, venue = rest.split(league, 1)
        target = norm(target)
        venue = dedupe_tail(venue)

    return Event(date, t, "試合", sport, league, target or "記載なし", venue, "記載なし", "記載なし", url)

def parse_page(date, line, url, title, page_sport):
    t, sport, rest = split_line(line)
    if sport == "記載なし":
        sport = page_sport

    event = norm(rest)
    if "|" in event:
        event = norm(event.split("|", 1)[0])

    if title != "記載なし" and title not in event:
        event = norm(f"{title} {event}")

    venue = "記載なし"
    parts = rest.split()
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        venue = parts[-1]

    return Event(date, t, "大会", sport, event or title, "大会のみ", venue, "記載なし", "記載なし", url)

def rows_by_lines(text, wanted):
    rows = []
    seen = set()
    current = None

    for raw in text.splitlines():
        line = norm(raw)
        if not line:
            continue
        d = iso_date(line)
        if d:
            current = d
            continue
        if current in wanted and re.match(r"^(\d{1,2}:\d{2}|終日|未定)\s+", line):
            key = (current, line)
            if key not in seen:
                seen.add(key)
                rows.append(key)
    return rows

def rows_by_blocks(text, wanted):
    """
    改行が崩れていても動くよう、全文から日付ブロックを切り出す。
    例:
      2026.06.30[火] 09:05 野球 カブス VS 09:05 パドレス MLB ...
      2026.07.01[水] ...
    """
    compact = norm(text)
    matches = list(DATE_RE.finditer(compact))
    rows = []
    seen = set()

    for i, m in enumerate(matches):
        date = iso_date(m.group(0))
        if date not in wanted:
            continue

        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(compact)
        block = compact[start:end]

        starts = list(EVENT_START_RE.finditer(block))
        for j, sm in enumerate(starts):
            s = sm.start()
            e = starts[j + 1].start() if j + 1 < len(starts) else len(block)
            candidate = norm(block[s:e])

            # フッターや検索文言が混ざりすぎないように、代表的な不要語で切る
            for stop in ["SEARCH", "MENU", "絞り込み", "この条件で絞り込む", "COPYRIGHT", "SHARE"]:
                if stop in candidate:
                    candidate = norm(candidate.split(stop, 1)[0])

            if candidate and re.match(r"^(\d{1,2}:\d{2}|終日|未定)\s+", candidate):
                key = (date, candidate)
                if key not in seen:
                    seen.add(key)
                    rows.append(key)

    return rows

def parse_url(url, html, wanted):
    soup = BeautifulSoup(html, "html.parser")
    title = title_of(soup)
    page_sport = find_sport(title + " " + soup.get_text(" ", strip=True)[:3000])
    is_team = "/team_and_players/" in url

    text_lines = soup.get_text("\n", strip=True)
    text_full = soup.get_text(" ", strip=True)

    rows = rows_by_lines(text_lines, wanted)
    if not rows:
        rows = rows_by_blocks(text_full, wanted)

    events = []
    for date, line in rows:
        try:
            if is_team:
                events.append(parse_team(date, line, url))
            else:
                events.append(parse_page(date, line, url, title, page_sport))
        except Exception:
            pass
    return events, {
        "url": url,
        "title": title,
        "rows": len(rows),
        "dates_in_page": sorted(set(filter(None, [iso_date(m.group(0)) for m in DATE_RE.finditer(text_full)])))[:10],
        "sample_rows": [r[1][:140] for r in rows[:3]],
    }

def dedupe(events):
    d = {}
    for e in events:
        if e.key() not in d:
            d[e.key()] = e

    def sk(e):
        m = re.match(r"^(\d{1,2}):(\d{2})", e.time)
        minutes = int(m.group(1)) * 60 + int(m.group(2)) if m else 9999
        return (e.date, minutes, e.sport, e.event, e.target)

    return sorted(d.values(), key=sk)

def load_existing():
    if not DATA_PATH.exists():
        return {}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save(payload):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    wanted = today_tomorrow()
    all_events = []
    errors = []
    debug = []
    fetched = 0
    parsed = 0

    for url in SOURCE_URLS:
        try:
            html = fetch(url)
            fetched += 1
            events, info = parse_url(url, html, wanted)
            debug.append(info)
            if events:
                parsed += 1
                all_events.extend(events)
            time.sleep(0.2)
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")

    events = dedupe(all_events)
    now = datetime.now(JST)

    if events:
        payload = {
            "generated_at": now.isoformat(timespec="seconds"),
            "timezone": "Asia/Tokyo",
            "source_name": "スポカレ",
            "source_urls": SOURCE_URLS,
            "target_dates": sorted(wanted),
            "events": [e.as_dict() for e in events],
            "last_update_note": f"自動取得成功。取得成功ページ数: {fetched}, 予定検出ページ数: {parsed}, 予定数: {len(events)}",
            "last_update_errors": errors[:30],
            "debug_info": debug[:12],
        }
    else:
        payload = load_existing()
        payload.setdefault("events", [])
        payload["generated_at"] = now.isoformat(timespec="seconds")
        payload["timezone"] = "Asia/Tokyo"
        payload["source_name"] = "スポカレ"
        payload["source_urls"] = SOURCE_URLS
        payload["target_dates"] = sorted(wanted)
        payload["last_update_note"] = f"新規取得0件のため既存データを維持。取得成功ページ数: {fetched}, 予定検出ページ数: {parsed}, 予定数: 0"
        payload["last_update_errors"] = errors[:30]
        payload["debug_info"] = debug[:12]

    save(payload)
    print(payload["last_update_note"])
    return 0 if fetched > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
