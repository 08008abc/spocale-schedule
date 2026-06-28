#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
スポカレ自動更新: Jina Reader フォールバック版

状況:
- GitHub Actions の requests ではスポカレのタイトルは取れるが、日付・予定一覧が本文に入らないことがある。
- その場合、https://r.jina.ai/https://... でページをMarkdown化してから再解析する。

出力:
- data/schedule.json
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
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
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
TIME_LINE_RE = re.compile(r"^(\d{1,2}:\d{2}|終日|未定)\s+")
TIME_ANY_RE = re.compile(r"(\d{1,2}:\d{2}|終日|未定)\s+")

EVENT_START_RE = re.compile(
    r"(?=(?:\d{1,2}:\d{2}|終日|未定)\s+(?:"
    + "|".join(map(re.escape, SPORTS))
    + r")\s+)"
)


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


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").replace("　", " ")).strip()


def wanted_dates():
    today = datetime.now(JST).date()
    return {today.isoformat(), (today + timedelta(days=1)).isoformat()}


def iso_from_date_text(text):
    m = DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{mo}-{d}"


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


def title_from_text(text, url):
    m = re.search(r"Title:\s*(.+)", text)
    if m:
        title = norm(m.group(1))
        title = title.replace("の日程一覧 | スポカレ", "")
        return title
    return "記載なし"


def fetch_direct_text(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    title = "記載なし"
    h2 = soup.find("h2")
    if h2 and norm(h2.get_text(" ", strip=True)):
        title = norm(h2.get_text(" ", strip=True))
    elif soup.find("title"):
        title = norm(soup.find("title").get_text(" ", strip=True)).replace("の日程一覧 | スポカレ", "")
    return soup.get_text("\n", strip=True), title, "direct"


def fetch_reader_text(url):
    # Jina Reader: URLの前に https://r.jina.ai/ を付ける
    reader_url = "https://r.jina.ai/" + url
    r = requests.get(reader_url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    text = r.text
    return text, title_from_text(text, url), "jina"


def fetch_best_text(url):
    text, title, mode = fetch_direct_text(url)
    if DATE_RE.search(text):
        return text, title, mode

    # 直接取得で予定日付が入らない場合はReader経由
    text2, title2, mode2 = fetch_reader_text(url)
    if DATE_RE.search(text2):
        return text2, title2 if title2 != "記載なし" else title, mode2

    return text, title, mode


def clean_line(line):
    line = norm(line)
    # Markdownリンク [text](url) の text 部分だけ残す
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    # Jina出力の余分な記号
    line = line.lstrip("*-# ")
    return norm(line)


def rows_by_lines(text, wanted):
    rows = []
    current = None
    seen = set()

    for raw in text.splitlines():
        line = clean_line(raw)
        if not line:
            continue

        d = iso_from_date_text(line)
        if d:
            current = d
            continue

        if current in wanted and TIME_LINE_RE.match(line):
            key = (current, line)
            if key not in seen:
                seen.add(key)
                rows.append(key)

    return rows


def rows_by_blocks(text, wanted):
    compact = norm(text)
    matches = list(DATE_RE.finditer(compact))
    rows = []
    seen = set()

    for i, m in enumerate(matches):
        date = iso_from_date_text(m.group(0))
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

            for stop in ["SEARCH", "MENU", "絞り込み", "この条件で絞り込む", "COPYRIGHT", "SHARE"]:
                if stop in candidate:
                    candidate = norm(candidate.split(stop, 1)[0])

            if candidate and TIME_LINE_RE.match(candidate):
                key = (date, candidate)
                if key not in seen:
                    seen.add(key)
                    rows.append(key)

    return rows


def split_line(line):
    line = clean_line(line)
    m = TIME_LINE_RE.match(line)
    if not m:
        return "記載なし", "記載なし", line

    time_text = m.group(1)
    rest = norm(line[m.end():])

    sport = find_sport(rest)
    if sport != "記載なし" and rest.startswith(sport):
        rest = norm(rest[len(sport):])

    return time_text, sport, rest


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

    # カブス VS 09:05 パドレス -> カブス vs パドレス
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


def parse_page_event(date, line, url, title, page_sport):
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


def parse_url(url, wanted):
    text, title, fetch_mode = fetch_best_text(url)
    page_sport = find_sport(title + " " + text[:3000])
    is_team = "/team_and_players/" in url

    rows = rows_by_lines(text, wanted)
    if not rows:
        rows = rows_by_blocks(text, wanted)

    events = []
    for date, line in rows:
        try:
            if is_team:
                events.append(parse_team(date, line, url))
            else:
                events.append(parse_page_event(date, line, url, title, page_sport))
        except Exception:
            pass

    debug = {
        "url": url,
        "title": title,
        "fetch_mode": fetch_mode,
        "rows": len(rows),
        "dates_in_page": sorted(set(filter(None, [iso_from_date_text(m.group(0)) for m in DATE_RE.finditer(text)])))[:12],
        "sample_rows": [r[1][:180] for r in rows[:3]],
    }
    return events, debug


def dedupe(events):
    by_key = {}
    for event in events:
        if event.key() not in by_key:
            by_key[event.key()] = event

    def sort_key(event):
        m = re.match(r"^(\d{1,2}):(\d{2})", event.time)
        minutes = int(m.group(1)) * 60 + int(m.group(2)) if m else 9999
        return (event.date, minutes, event.sport, event.event, event.target)

    return sorted(by_key.values(), key=sort_key)


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
    wanted = wanted_dates()
    all_events = []
    errors = []
    debug_info = []
    fetched = 0
    parsed = 0

    for url in SOURCE_URLS:
        try:
            events, debug = parse_url(url, wanted)
            fetched += 1
            debug_info.append(debug)

            if events:
                parsed += 1
                all_events.extend(events)

            # Jina Readerの負荷・レート制限対策
            time.sleep(0.35)
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
            "debug_info": debug_info[:20],
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
        payload["debug_info"] = debug_info[:20]

    save(payload)
    print(payload["last_update_note"])
    return 0 if fetched > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
