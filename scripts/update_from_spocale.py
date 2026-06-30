#!/usr/bin/env python3
"""
スポカレ 今日＋明日 自動更新・厳密取得版

修正点:
1. 登録していない予定が混ざらないように、各URLの「試合一覧」本文だけを読む
2. 一覧ページから拾った game 詳細ページを開き、テレビ放送・ネット配信を詳細ページから読む
3. 毎回、日本時間の今日＋明日だけを対象にする
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "schedule.json"
BASE = "https://spocale.com"

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

SPORT_BY_ID = {
    "1": "野球", "2": "サッカー", "3": "ラグビー", "5": "バスケットボール",
    "6": "ゴルフ", "7": "陸上競技", "8": "テニス", "9": "競馬",
    "11": "モータースポーツ", "14": "バレーボール", "18": "バドミントン",
    "22": "競艇", "32": "卓球", "43": "アメリカンフットボール",
    "44": "フィギュアスケート", "50": "スケートボード", "51": "BMX", "52": "スポーツクライミング",
}

GENERIC_STOP_WORDS = {
    "TOP", "試合一覧", "絞込み検索", "絞込み", "チーム一覧", "大会・リーグ一覧",
    "SEARCH", "MENU", "通知設定", "この試合を通知する", "関連カレンダー",
    "スポーツ日程更新中", "スポカレ", "無料ダウンロード"
}


def now_jst() -> datetime:
    return datetime.now(JST)


def target_dates() -> list[str]:
    d = now_jst().date()
    return [d.isoformat(), (d + timedelta(days=1)).isoformat()]


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(url: str) -> str:
    last: Exception | None = None
    for i in range(3):
        try:
            r = requests.get(
                url,
                timeout=25,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; spocale-schedule/3.0)",
                    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                },
            )
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last = exc
            time.sleep(1 + i)
    raise RuntimeError(str(last))


def sport_from_url(url: str) -> str:
    m = re.search(r"/sports/(\d+)", url)
    return SPORT_BY_ID.get(m.group(1), "記載なし") if m else "記載なし"


def is_team_page(url: str) -> bool:
    return "/team_and_players/" in url


def page_name(soup: BeautifulSoup) -> str:
    for selector in ["h1", "h2", "title"]:
        node = soup.select_one(selector)
        if node:
            text = clean(node.get_text(" ", strip=True)).replace(" | スポカレ", "")
            if text and text != "スポカレ スポーツ日程更新中":
                return text
    return "記載なし"


def iso_from_date_text(text: str) -> str | None:
    m = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def main_area_game_links(soup: BeautifulSoup, dates: set[str]) -> list[dict[str, str]]:
    body = soup.body or soup
    active = False
    current_date: str | None = None
    results: list[dict[str, str]] = []

    def text_of(node: Any) -> str:
        if isinstance(node, NavigableString):
            return clean(str(node))
        if isinstance(node, Tag):
            return clean(node.get_text(" ", strip=True))
        return ""

    for node in body.descendants:
        if not isinstance(node, (NavigableString, Tag)):
            continue

        text = text_of(node)
        if not text:
            continue

        if not active:
            if text in {"チーム一覧", "大会・リーグ一覧"} or "絞込み検索" in text:
                active = True
            continue

        if text == "SEARCH" or text == "MENU" or text.startswith("この条件で絞り込む") or text == "SCROLL TO TOP":
            break

        date_iso = iso_from_date_text(text)
        if date_iso:
            current_date = date_iso

        if isinstance(node, Tag) and node.name == "a":
            href = node.get("href") or ""
            if "/game/" not in href:
                continue
            if not current_date or current_date not in dates:
                continue
            entry = clean(node.get_text(" ", strip=True))
            if not re.search(r"(\d{1,2}:\d{2}|未定|終日)", entry):
                continue
            results.append({
                "date": current_date,
                "entry": entry,
                "game_url": urljoin(BASE, href),
            })
    return results


def normalize_time(text: str) -> str:
    m = re.search(r"(\d{1,2}:\d{2}|未定|終日)", text)
    if not m:
        return "記載なし"
    t = m.group(1)
    if re.match(r"^\d{1,2}:\d{2}$", t):
        h, mm = t.split(":")
        return f"{int(h):02d}:{mm}"
    return t


def split_list_entry(entry: str, sport: str) -> dict[str, str]:
    time_value = normalize_time(entry)
    text = clean(entry)
    text = re.sub(r"^(\d{1,2}:\d{2}|未定|終日)\s*", "", text)
    if sport and sport != "記載なし":
        text = re.sub(rf"^{re.escape(sport)}\s*", "", text)
    text = re.sub(r"\s+VS\s+(\d{1,2}:\d{2}|未定|終日)\s+", " vs ", text)
    text = text.replace(" VS ", " vs ")
    if "|" in text:
        left, right = [clean(x) for x in text.split("|", 1)]
    else:
        left, right = text, ""
    return {"time": time_value, "raw_title": clean(left), "raw_detail": clean(right)}


def detail_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    lines = []
    for s in soup.get_text("\n", strip=True).splitlines():
        t = clean(s)
        if t and t not in GENERIC_STOP_WORDS:
            lines.append(t)
    return lines


def detail_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title")
    if not title:
        return ""
    text = clean(title.get_text(" ", strip=True)).replace(" | スポカレ", "")
    text = re.sub(r"\s*日時・.*?情報\s*", " ", text)
    return clean(text)


def clean_provider(line: str) -> str:
    text = clean(line)
    text = re.sub(r"\bLIVE\b", "", text)
    text = text.replace("見逃し", "")
    text = text.replace("録画", "")
    text = re.sub(r"\d{1,2}:\d{2}\s*~", "", text)
    return clean(text)


def providers_between(lines: list[str], start_word: str, end_words: list[str]) -> str:
    providers: list[str] = []
    active = False
    for line in lines:
        if start_word in line:
            active = True
            continue
        if active and any(w in line for w in end_words):
            break
        if not active:
            continue
        p = clean_provider(line)
        if not p or p in {"LIVE", "見逃し", "録画"}:
            continue
        if re.match(r"^\d{1,2}:\d{2}\s*~", p):
            continue
        if p in GENERIC_STOP_WORDS:
            continue
        if "通知" in p or "カレンダー" in p or "関連" in p:
            continue
        providers.append(p)
    return "、".join(dict.fromkeys(providers)) if providers else "記載なし"


def media_from_detail(lines: list[str]) -> tuple[str, str]:
    tv = providers_between(lines, "TV放送情報", ["配信情報", "関連カレンダー", "SEARCH"])
    stream = providers_between(lines, "配信情報", ["関連カレンダー", "SEARCH", "MENU"])
    return tv, stream


def sport_event_from_detail(lines: list[str], fallback_sport: str, fallback_event: str) -> tuple[str, str]:
    for line in lines:
        for sport in SPORT_BY_ID.values():
            if line.startswith(sport + " "):
                event = clean(line[len(sport):])
                return sport, event or fallback_event
    return fallback_sport, fallback_event


def parse_title_match(base_title: str) -> tuple[str, str]:
    if " vs " not in base_title:
        return base_title or "記載なし", "大会のみ"
    before, after = base_title.split(" vs ", 1)
    parts = before.split(" ")
    if len(parts) >= 2:
        event = " ".join(parts[:-1])
        home = parts[-1]
    else:
        event = "記載なし"
        home = before
    return clean(event), clean(f"{home} vs {after}")


def venue_from_detail(lines: list[str], target: str) -> str:
    for i, line in enumerate(lines):
        if re.search(r"20\d{2}\.\d{2}\.\d{2}\s+(\d{1,2}:\d{2}|未定|終日)", line):
            for c in lines[i + 1:i + 5]:
                if c in GENERIC_STOP_WORDS:
                    continue
                if c in target:
                    continue
                if "カレンダー" in c or "通知" in c:
                    continue
                if len(c) <= 40:
                    return c
    return "記載なし"


def fallback_event_from_entry(source_url: str, source_name: str, date: str, entry: str, game_url: str) -> dict[str, Any]:
    sport = sport_from_url(source_url)
    pieces = split_list_entry(entry, sport)
    raw_title = pieces["raw_title"]
    raw_detail = pieces["raw_detail"]
    if is_team_page(source_url):
        event, target = parse_title_match(raw_title)
        item_type = "試合"
    else:
        event = raw_title or source_name
        target = "大会のみ"
        item_type = "大会"
    venue = "記載なし"
    if raw_detail:
        d = raw_detail
        for x in [event, target, source_name]:
            d = d.replace(x, " ")
        d = clean(d)
        parts = d.split(" ")
        if len(parts) >= 2 and len(parts) % 2 == 0:
            half = len(parts) // 2
            if parts[:half] == parts[half:]:
                d = " ".join(parts[:half])
        venue = d or "記載なし"
    return {
        "date": date,
        "time": pieces["time"],
        "type": item_type,
        "sport": sport,
        "event": event or "記載なし",
        "target": target or "記載なし",
        "venue": venue,
        "tv": "記載なし",
        "stream": "記載なし",
        "source": source_url,
        "game_url": game_url,
    }


def parse_detail(game_url: str, fallback: dict[str, Any], source_url: str, page_type: str) -> dict[str, Any]:
    html = fetch(game_url)
    lines = detail_lines(html)
    title = detail_title(html)
    sport, event_from_line = sport_event_from_detail(lines, fallback["sport"], fallback.get("event", "記載なし"))
    event_from_title, target_from_title = parse_title_match(title)
    if page_type == "event":
        item_type = "大会"
        event = event_from_title if target_from_title == "大会のみ" else event_from_line
        target = "大会のみ"
    else:
        item_type = "試合"
        event = event_from_title if event_from_title != "記載なし" else event_from_line
        target = target_from_title if target_from_title != "大会のみ" else fallback.get("target", "記載なし")
    tv, stream = media_from_detail(lines)
    venue = venue_from_detail(lines, target)
    if venue == "記載なし":
        venue = fallback.get("venue", "記載なし")
    return {
        "date": fallback["date"],
        "time": fallback["time"],
        "type": item_type,
        "sport": sport,
        "event": event or "記載なし",
        "target": target or "記載なし",
        "venue": venue or "記載なし",
        "tv": tv,
        "stream": stream,
        "source": source_url,
        "game_url": game_url,
    }


def parse_source_url(source_url: str, dates: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    html = fetch(source_url)
    soup = BeautifulSoup(html, "html.parser")
    name = page_name(soup)
    page_type = "team" if is_team_page(source_url) else "event"
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in main_area_game_links(soup, dates):
        fallback = fallback_event_from_entry(source_url, name, item["date"], item["entry"], item["game_url"])
        try:
            events.append(parse_detail(item["game_url"], fallback, source_url, page_type))
        except Exception as exc:
            errors.append(f"{item['game_url']}: detail fetch failed: {type(exc).__name__}: {exc}")
            events.append(fallback)
    return events, errors


def time_minutes(t: str) -> int:
    if re.match(r"^\d{2}:\d{2}$", t or ""):
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    if t == "終日":
        return 9997
    if t == "未定":
        return 9998
    return 9999


def dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for e in events:
        key = (e.get("date", ""), e.get("time", ""), e.get("type", ""), e.get("sport", ""), e.get("target", ""))
        if key not in result:
            result[key] = e
            continue
        base = result[key]
        for field in ["event", "venue", "tv", "stream", "game_url", "source"]:
            if base.get(field) in {"", "記載なし", None} and e.get(field) not in {"", "記載なし", None}:
                base[field] = e[field]
    return sorted(result.values(), key=lambda e: (e.get("date", ""), time_minutes(e.get("time", "")), e.get("sport", ""), e.get("target", "")))


def write_json(events: list[dict[str, Any]], target: list[str], errors: list[str]) -> None:
    payload = {
        "generated_at": now_jst().isoformat(timespec="seconds"),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "display_rule": "毎日0時に日本時間の実行日当日と翌日の2日分へ更新",
        "target_dates": target,
        "events": events,
        "last_update_note": f"{target[0]} と {target[1]} の予定を {len(events)} 件取得しました。",
        "last_update_errors": errors[:100],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    target = target_dates()
    date_set = set(target)
    all_events: list[dict[str, Any]] = []
    all_errors: list[str] = []
    for source_url in SOURCE_URLS:
        try:
            events, errors = parse_source_url(source_url, date_set)
            all_events.extend(events)
            all_errors.extend(errors)
        except Exception as exc:
            all_errors.append(f"{source_url}: {type(exc).__name__}: {exc}")
    events = dedupe(all_events)
    write_json(events, target, all_errors)
    print(f"updated target_dates={target}, events={len(events)}, errors={len(all_errors)}")


if __name__ == "__main__":
    main()
