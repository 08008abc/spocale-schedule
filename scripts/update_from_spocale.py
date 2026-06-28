#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
スポカレ自動更新: 初期HTMLレスポンス解析版

ネットワーク調査の結果、予定データはAPIではなく
最初に返るHTMLレスポンス本文に含まれていることが分かったため、
Playwrightでページを開いた後のDOMではなく、main document response.text() を解析します。
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


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

SPORTS = [
    "バレーボール", "バスケットボール", "バドミントン", "フィギュアスケート",
    "サッカー", "ラグビー", "テニス", "ゴルフ", "陸上競技", "野球",
    "卓球", "競泳", "相撲", "柔道", "ボクシング", "格闘技", "体操",
    "ハンドボール", "モータースポーツ", "ソフトボール", "アイスホッケー",
    "ホッケー", "ビーチバレー",
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
    match = DATE_RE.search(text)
    if not match:
        return None
    y, mo, d = match.groups()
    return f"{y}-{mo}-{d}"


def find_sport(text):
    for sport in SPORTS:
        if sport in text:
            return sport
    return "記載なし"


def find_league(text):
    for league in LEAGUES:
        if league in text:
            return league
    return "記載なし"


def title_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    h2 = soup.find("h2")
    if h2 and norm(h2.get_text(" ", strip=True)):
        return norm(h2.get_text(" ", strip=True))
    title = soup.find("title")
    if title:
        return norm(title.get_text(" ", strip=True)).replace("の日程一覧 | スポカレ", "")
    return "記載なし"


def clean_line(line):
    line = norm(line)
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    line = line.lstrip("*-# ")
    return norm(line)


def lines_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return [clean_line(x) for x in soup.get_text("\n", strip=True).splitlines() if clean_line(x)]


def rows_from_lines(lines, wanted):
    rows = []
    current_date = None
    seen = set()

    for line in lines:
        date = iso_from_date_text(line)
        if date:
            current_date = date
            continue

        if current_date in wanted and TIME_LINE_RE.match(line):
            key = (current_date, line)
            if key not in seen:
                seen.add(key)
                rows.append(key)

    return rows


def split_line(line):
    line = clean_line(line)
    match = TIME_LINE_RE.match(line)
    if not match:
        return "記載なし", "記載なし", line

    time_text = match.group(1)
    rest = norm(line[match.end():])

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


def parse_team_event(date, line, url):
    time_text, sport, rest = split_line(line)
    rest = re.sub(r"\b(VS|Vs|vs)\s+\d{1,2}:\d{2}\b", "vs", rest)
    rest = norm(rest.replace(" VS ", " vs ").replace("VS", "vs").replace("Vs", "vs"))

    league = find_league(rest)
    target = rest
    venue = "記載なし"

    if league != "記載なし" and league in rest:
        target, venue = rest.split(league, 1)
        target = norm(target)
        venue = dedupe_tail(venue)

    return Event(date, time_text, "試合", sport, league, target or "記載なし", venue or "記載なし", "記載なし", "記載なし", url)


def parse_page_event(date, line, url, title, page_sport):
    time_text, sport, rest = split_line(line)
    if sport == "記載なし":
        sport = page_sport

    event_name = norm(rest)
    if "|" in event_name:
        event_name = norm(event_name.split("|", 1)[0])

    if title != "記載なし" and title not in event_name:
        event_name = norm(f"{title} {event_name}")

    venue = "記載なし"
    parts = rest.split()
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        venue = parts[-1]

    return Event(date, time_text, "大会", sport, event_name or title, "大会のみ", venue, "記載なし", "記載なし", url)


def parse_html(url, html, wanted):
    title = title_from_html(html)
    lines = lines_from_html(html)
    rows = rows_from_lines(lines, wanted)

    page_sport = find_sport(title + " " + " ".join(lines[:100]))
    is_team_page = "/team_and_players/" in url

    events = []
    for date, line in rows:
        try:
            if is_team_page:
                events.append(parse_team_event(date, line, url))
            else:
                events.append(parse_page_event(date, line, url, title, page_sport))
        except Exception:
            pass

    dates_in_page = []
    for line in lines:
        d = iso_from_date_text(line)
        if d and d not in dates_in_page:
            dates_in_page.append(d)

    return events, {
        "url": url,
        "title": title,
        "fetch_mode": "initial_html_response",
        "rows": len(rows),
        "dates_in_page": dates_in_page[:20],
        "sample_rows": [row[1][:220] for row in rows[:5]],
        "line_sample": lines[110:140] if len(lines) > 140 else lines[:80],
    }


async def fetch_initial_html(page, url):
    response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    if response is None:
        raise RuntimeError("No main document response")
    return await response.text()


def dedupe(events):
    by_key = {}
    for event in events:
        if event.key() not in by_key:
            by_key[event.key()] = event

    def sort_key(event):
        match = re.match(r"^(\d{1,2}):(\d{2})", event.time)
        minutes = int(match.group(1)) * 60 + int(match.group(2)) if match else 9999
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


async def run():
    wanted = wanted_dates()
    all_events = []
    errors = []
    debug_info = []
    fetched = 0
    parsed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        for url in SOURCE_URLS:
            try:
                html = await fetch_initial_html(page, url)
                fetched += 1

                events, debug = parse_html(url, html, wanted)
                debug_info.append(debug)

                if events:
                    parsed += 1
                    all_events.extend(events)

                await page.wait_for_timeout(250)

            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")

        await browser.close()

    events = dedupe(all_events)
    now = datetime.now(JST)

    if events:
        payload = {
            "generated_at": now.isoformat(timespec="seconds"),
            "timezone": "Asia/Tokyo",
            "source_name": "スポカレ",
            "source_urls": SOURCE_URLS,
            "target_dates": sorted(wanted),
            "events": [event.as_dict() for event in events],
            "last_update_note": f"初期HTMLレスポンスから自動取得成功。取得成功ページ数: {fetched}, 予定検出ページ数: {parsed}, 予定数: {len(events)}",
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
        payload["last_update_note"] = f"初期HTMLレスポンスでも新規取得0件。取得成功ページ数: {fetched}, 予定検出ページ数: {parsed}, 予定数: 0"
        payload["last_update_errors"] = errors[:30]
        payload["debug_info"] = debug_info[:20]

    save(payload)
    print(payload["last_update_note"])
    return 0 if fetched > 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
