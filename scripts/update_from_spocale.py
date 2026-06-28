#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
スポカレ自動更新: 分割行解析版

スポカレの初期HTMLでは、予定が以下のように分割行で入ることがある。

2026.06.30
[火]
09:05
野球
カブス
VS
09:05
パドレス
MLB
リグレー・フィールド
リグレー・フィールド

この形式に合わせて、日付・曜日・時刻・競技・対象・リーグ・会場を順番に読む。
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

DATE_RE = re.compile(r"^(20\d{2})\.(\d{2})\.(\d{2})$")
DATE_INLINE_RE = re.compile(r"(20\d{2})\.(\d{2})\.(\d{2})")
WEEKDAY_RE = re.compile(r"^\[[月火水木金土日]\]$")
TIME_RE = re.compile(r"^(\d{1,2}:\d{2}|終日|未定)$")

STOP_WORDS = {
    "過去の試合日程", "スポカレ", "MENU", "無料アプリ", "公式Twitter", "公式Facebook",
    "利用規約", "プライバシーポリシー", "運営会社", "アプリ版スポカレの", "無料ダウンロード",
}


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


def iso_from_date_line(line):
    m = DATE_RE.match(line)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{mo}-{d}"


def is_date_line(line):
    return bool(DATE_RE.match(line))


def is_time_line(line):
    return bool(TIME_RE.match(line))


def is_sport_line(line):
    return line in SPORTS


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

    lines = []
    for raw in soup.get_text("\n", strip=True).splitlines():
        line = clean_line(raw)
        if not line:
            continue
        lines.append(line)
    return lines


def find_next_date_index(lines, start):
    for i in range(start, len(lines)):
        if is_date_line(lines[i]) or lines[i] in STOP_WORDS:
            return i
    return len(lines)


def infer_page_sport(title, lines):
    joined = " ".join([title] + lines[:120])
    for sport in SPORTS:
        if sport in joined:
            return sport
    return "記載なし"


def parse_split_block(date, block, url, title, is_team_page, page_sport):
    """
    block example:
      [火], 09:05, 野球, カブス, VS, 09:05, パドレス, MLB, リグレー...
    """
    # 曜日行を除去
    block = [x for x in block if not WEEKDAY_RE.match(x)]
    if not block:
        return None

    # 最初の時刻を探す
    time_idx = None
    for i, x in enumerate(block):
        if is_time_line(x):
            time_idx = i
            break
    if time_idx is None:
        return None

    time_text = block[time_idx]
    if time_idx + 1 >= len(block):
        return None

    sport = block[time_idx + 1] if is_sport_line(block[time_idx + 1]) else page_sport
    pos = time_idx + 2 if is_sport_line(block[time_idx + 1]) else time_idx + 1

    # チームページは 対象A / VS / 時刻 / 対象B / リーグ / 詳細 / 会場 / 会場 の順が多い
    if is_team_page:
        if pos >= len(block):
            return None

        left = block[pos] if pos < len(block) else "記載なし"
        target = left
        event = "記載なし"
        venue = "記載なし"

        if pos + 1 < len(block) and block[pos + 1].upper() == "VS":
            # VS の後ろに時刻が重複して入る場合がある
            right_idx = pos + 2
            if right_idx < len(block) and is_time_line(block[right_idx]):
                right_idx += 1
            right = block[right_idx] if right_idx < len(block) else "記載なし"
            target = f"{left} vs {right}"
            after_idx = right_idx + 1
        else:
            after_idx = pos + 1

        if after_idx < len(block):
            event = block[after_idx]

        # "| 第○節" などがあれば大会名に付ける
        if after_idx + 1 < len(block) and block[after_idx + 1].startswith("|"):
            event = f"{event} {block[after_idx + 1]}"

        # 会場は後ろの方の非日付・非時刻・非スポーツのもの
        tail = [x for x in block[after_idx + 1:] if not is_time_line(x) and not is_sport_line(x) and not x.startswith("|")]
        if tail:
            venue = tail[-1]
            if len(tail) >= 2 and tail[-1] == tail[-2]:
                venue = tail[-1]

        return Event(date, time_text, "試合", sport, event, target, venue, "記載なし", "記載なし", url)

    # sports / leagues ページは大会として扱う
    else:
        rest = block[pos:]
        event_name = " ".join(rest[:4]) if rest else title
        venue = "記載なし"
        if len(rest) >= 2 and rest[-1] == rest[-2]:
            venue = rest[-1]
        elif rest:
            venue = rest[-1]

        return Event(date, time_text, "大会", sport, event_name or title, "大会のみ", venue, "記載なし", "記載なし", url)


def rows_from_split_lines(lines, wanted, url, title):
    is_team_page = "/team_and_players/" in url
    page_sport = infer_page_sport(title, lines)

    events = []
    debug_rows = []

    i = 0
    while i < len(lines):
        line = lines[i]
        date = iso_from_date_line(line)

        if not date:
            i += 1
            continue

        next_i = find_next_date_index(lines, i + 1)
        block = lines[i + 1:next_i]

        if date in wanted:
            event = parse_split_block(date, block, url, title, is_team_page, page_sport)
            if event:
                events.append(event)
                debug_rows.append({
                    "date": date,
                    "block": block[:14],
                    "parsed": event.as_dict(),
                })

        i = next_i

    return events, debug_rows


def parse_html(url, html, wanted):
    title = title_from_html(html)
    lines = lines_from_html(html)
    events, debug_rows = rows_from_split_lines(lines, wanted, url, title)

    dates_in_page = []
    for line in lines:
        d = iso_from_date_line(line)
        if d and d not in dates_in_page:
            dates_in_page.append(d)

    return events, {
        "url": url,
        "title": title,
        "fetch_mode": "split_lines_initial_html",
        "rows": len(events),
        "dates_in_page": dates_in_page[:30],
        "sample_rows": debug_rows[:5],
        "line_sample": lines[100:135] if len(lines) > 135 else lines[:80],
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
            "last_update_note": f"分割行HTMLから自動取得成功。取得成功ページ数: {fetched}, 予定検出ページ数: {parsed}, 予定数: {len(events)}",
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
        payload["last_update_note"] = f"分割行HTMLでも新規取得0件。取得成功ページ数: {fetched}, 予定検出ページ数: {parsed}, 予定数: 0"
        payload["last_update_errors"] = errors[:30]
        payload["debug_info"] = debug_info[:20]

    save(payload)
    print(payload["last_update_note"])
    return 0 if fetched > 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
