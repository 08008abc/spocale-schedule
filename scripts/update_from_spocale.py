#!/usr/bin/env python3
"""
スポカレ 今日＋明日 自動更新 完成版

目的:
- GitHub Actionsで毎日0時過ぎ（日本時間）に実行
- data/schedule.json を必ず「日本時間の今日＋明日」に更新
- 対象URLから該当日の予定だけを取得して events に反映
- team_and_players は個別試合として扱う
- sports / leagues は大会・イベントとして扱う
- 取得できないURLや解析失敗は last_update_errors に記録
- 古い events を別日付として表示し続けない
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

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

SPORT_BY_ID = {
    "1": "野球",
    "2": "サッカー",
    "3": "ラグビー",
    "5": "バスケットボール",
    "6": "ゴルフ",
    "7": "陸上競技",
    "8": "テニス",
    "9": "競馬",
    "11": "モータースポーツ",
    "14": "バレーボール",
    "18": "バドミントン",
    "22": "競艇",
    "32": "卓球",
    "43": "アメリカンフットボール",
    "44": "フィギュアスケート",
    "50": "スケートボード",
    "51": "BMX",
    "52": "スポーツクライミング",
}

LEAGUE_WORDS = [
    "MLB",
    "B.PREMIER",
    "Bリーグ",
    "WEリーグ",
    "なでしこリーグ",
    "Jリーグ",
    "プレミアリーグ",
    "FIFA",
    "ワールドカップ",
    "ネーションズリーグ",
    "Vリーグ",
    "SVリーグ",
    "リーグワン",
    "BWFワールドツアー",
    "JLPGAツアー",
    "ダイヤモンドリーグ",
]


@dataclass
class PageContext:
    url: str
    name: str
    sport: str
    page_type: str  # team or event


def now_jst() -> datetime:
    return datetime.now(JST)


def target_dates() -> list[str]:
    today = now_jst().date()
    return [today.isoformat(), (today + timedelta(days=1)).isoformat()]


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_team_page(url: str) -> bool:
    return "/team_and_players/" in url


def sport_from_url(url: str) -> str:
    m = re.search(r"/sports/(\d+)", url)
    if m:
        return SPORT_BY_ID.get(m.group(1), "記載なし")
    return "記載なし"


def fetch(url: str) -> str:
    last_error: Exception | None = None
    for i in range(3):
        try:
            res = requests.get(
                url,
                timeout=25,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; spocale-daily-page/2.0; +https://github.com/)",
                    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                },
            )
            res.raise_for_status()
            return res.text
        except Exception as exc:
            last_error = exc
            time.sleep(1 + i)
    raise RuntimeError(str(last_error))


def page_name(soup: BeautifulSoup) -> str:
    for selector in ["h1", "h2", "title"]:
        node = soup.select_one(selector)
        if node:
            txt = clean(node.get_text(" ", strip=True)).replace(" | スポカレ", "")
            if txt and txt not in {"スポカレ スポーツ日程更新中"}:
                return txt
    return "スポカレ予定"


def page_context(url: str, soup: BeautifulSoup) -> PageContext:
    return PageContext(
        url=url,
        name=page_name(soup),
        sport=sport_from_url(url),
        page_type="team" if is_team_page(url) else "event",
    )


def iso_from_spocale_date(text: str) -> str | None:
    m = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", text)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def extract_schedule_lines(soup: BeautifulSoup) -> list[tuple[str, str, str]]:
    """
    return [(date_iso, entry_text, href), ...]

    スポカレの一覧は「日付見出し → /sports/.../game/... のリンク」という構造が多い。
    BeautifulSoupのDOM順にテキストを見ながら、直前の日付をゲームリンクへ紐付ける。
    """
    records: list[tuple[str, str, str]] = []
    current_date: str | None = None

    # DOM順に、日付らしいテキストとゲームリンクを拾う
    for node in soup.find_all(["h2", "h3", "h4", "div", "p", "li", "a", "span"]):
        text = clean(node.get_text(" ", strip=True))
        if not text:
            continue

        date = iso_from_spocale_date(text)
        if date:
            current_date = date

        if node.name == "a":
            href = node.get("href") or ""
            full_href = urljoin("https://spocale.com", href)
            is_game_link = "/game/" in href or re.search(r"/sports/\d+/game/\d+", href)
            has_time = bool(re.search(r"(\d{1,2}:\d{2}|未定|終日)", text))
            if current_date and is_game_link and has_time:
                records.append((current_date, text, full_href))

    # フォールバック: DOMから取れなかった場合、ページ全文の行を順番に見る
    if not records:
        current_date = None
        for line in soup.get_text("\n", strip=True).splitlines():
            line = clean(line)
            if not line:
                continue
            date = iso_from_spocale_date(line)
            if date:
                current_date = date
                continue
            if current_date and re.search(r"(\d{1,2}:\d{2}|未定|終日)", line):
                # メニュー等を避けるため、競技名っぽい語がある行だけ
                if any(s in line for s in SPORT_BY_ID.values()) or "VS" in line or "オープン" in line or "大会" in line:
                    records.append((current_date, line, ""))

    return records


def normalize_time(entry: str) -> str:
    m = re.search(r"(\d{1,2}:\d{2}|未定|終日)", entry)
    if not m:
        return "記載なし"
    t = m.group(1)
    if re.match(r"^\d{1,2}:\d{2}$", t):
        h, mm = t.split(":")
        return f"{int(h):02d}:{mm}"
    return t


def remove_first_time_and_sport(entry: str, sport: str) -> str:
    text = clean(entry)
    text = re.sub(r"^(\d{1,2}:\d{2}|未定|終日)\s*", "", text)
    if sport != "記載なし":
        text = re.sub(rf"^{re.escape(sport)}\s*", "", text)
    return clean(text)


def detect_league(text: str, fallback: str) -> str:
    for word in LEAGUE_WORDS:
        if word in text:
            return word
    if fallback and fallback != "スポカレ予定":
        return fallback
    return "記載なし"


def strip_duplicate_venue(venue: str) -> str:
    venue = clean(venue)
    if venue == "記載なし":
        return venue
    tokens = venue.split()
    half = len(tokens) // 2
    if half > 0 and len(tokens) % 2 == 0 and tokens[:half] == tokens[half:]:
        return " ".join(tokens[:half])
    # よくある「カナダ カナダ」「リグレー・フィールド リグレー・フィールド」を圧縮
    parts = venue.split(" ")
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        return parts[-1]
    return venue


def guess_stream(text: str) -> str:
    words = [
        "YouTubeLive", "YouTube", "U-NEXT", "DAZN", "ABEMA de DAZN", "ABEMA",
        "Lemino", "SPOTV NOW", "MLB.TV", "Amazon Prime Video",
        "VOLLEYBALL TV", "J SPORTSオンデマンド", "ゴルフネットワークプラス"
    ]
    found = [w for w in words if w in text]
    return "、".join(dict.fromkeys(found)) if found else "記載なし"


def guess_tv(text: str) -> str:
    words = [
        "NHK BS4K", "NHK BS", "NHK", "BS-TBS", "BS10", "BS", "フジテレビ",
        "日本テレビ", "TBS", "テレビ朝日", "テレビ東京", "WOWOW",
        "J SPORTS", "ゴルフネットワーク"
    ]
    found = [w for w in words if w in text]
    return "、".join(dict.fromkeys(found)) if found else "記載なし"


def parse_team_entry(ctx: PageContext, date: str, entry: str, href: str) -> dict[str, Any]:
    time_value = normalize_time(entry)
    rest = remove_first_time_and_sport(entry, ctx.sport)

    # 「カブス VS 09:05 パドレス」を「カブス vs パドレス」にする
    rest = re.sub(r"\s+VS\s+(\d{1,2}:\d{2}|未定|終日)\s+", " vs ", rest)
    rest = rest.replace(" VS ", " vs ")

    league = detect_league(rest, "記載なし")
    before_league = rest
    after_league = ""
    if league != "記載なし" and league in rest:
        before_league, after_league = rest.split(league, 1)

    target = clean(before_league) or ctx.name
    venue = strip_duplicate_venue(after_league) if after_league else "記載なし"

    return {
        "date": date,
        "time": time_value,
        "type": "試合",
        "sport": ctx.sport,
        "event": league,
        "target": target,
        "venue": venue or "記載なし",
        "tv": guess_tv(entry),
        "stream": guess_stream(entry),
        "source": href or ctx.url,
    }


def parse_event_entry(ctx: PageContext, date: str, entry: str, href: str) -> dict[str, Any]:
    time_value = normalize_time(entry)
    rest = remove_first_time_and_sport(entry, ctx.sport)

    # 例: カナダ・オープン 2日目 BWFワールドツアー | カナダ・オープン 2日目 カナダ カナダ
    if "|" in rest:
        left, right = [clean(x) for x in rest.split("|", 1)]
    else:
        left, right = rest, ""

    event_name = left or ctx.name
    league = detect_league(event_name, ctx.name)
    venue = "記載なし"

    if right:
        # rightからイベント名の重複を取り除き、最後に残る会場らしい部分を使う
        right2 = right
        for token in [event_name, league, ctx.name]:
            if token and token != "記載なし":
                right2 = right2.replace(token, " ")
        venue = strip_duplicate_venue(right2)

    return {
        "date": date,
        "time": time_value,
        "type": "大会",
        "sport": ctx.sport,
        "event": event_name,
        "target": "大会のみ",
        "venue": venue or "記載なし",
        "tv": guess_tv(entry),
        "stream": guess_stream(entry),
        "source": href or ctx.url,
    }


def parse_url(url: str, dates: set[str]) -> list[dict[str, Any]]:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    ctx = page_context(url, soup)

    events: list[dict[str, Any]] = []
    for date, entry, href in extract_schedule_lines(soup):
        if date not in dates:
            continue
        if ctx.page_type == "team":
            events.append(parse_team_entry(ctx, date, entry, href))
        else:
            events.append(parse_event_entry(ctx, date, entry, href))

    return events


def event_sort_key(e: dict[str, Any]) -> tuple[str, int, str, str]:
    t = e.get("time", "")
    if re.match(r"^\d{2}:\d{2}$", t):
        h, m = t.split(":")
        minutes = int(h) * 60 + int(m)
    elif t == "終日":
        minutes = 9997
    elif t == "未定":
        minutes = 9998
    else:
        minutes = 9999
    return (e.get("date", ""), minutes, e.get("sport", ""), e.get("target", ""))


def dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}

    for e in events:
        key = (
            e.get("date", ""),
            e.get("time", ""),
            e.get("type", ""),
            e.get("sport", ""),
            e.get("target", ""),
        )
        if key not in merged:
            merged[key] = e
            continue

        # 既存より詳しい情報があれば補完
        base = merged[key]
        for field in ["event", "venue", "tv", "stream", "source"]:
            if base.get(field) in {"", "記載なし", None} and e.get(field) not in {"", "記載なし", None}:
                base[field] = e[field]

    return sorted(merged.values(), key=event_sort_key)


def write_schedule(events: list[dict[str, Any]], target: list[str], errors: list[str]) -> None:
    payload = {
        "generated_at": now_jst().isoformat(timespec="seconds"),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "display_rule": "毎日0時に日本時間の実行日当日と翌日の2日分へ更新",
        "target_dates": target,
        "events": events,
        "last_update_note": (
            f"{target[0]} と {target[1]} の予定を {len(events)} 件取得しました。"
            if events else
            f"{target[0]} と {target[1]} の対象予定は0件、または取得できませんでした。"
        ),
        "last_update_errors": errors[:80],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    target = target_dates()
    date_set = set(target)

    all_events: list[dict[str, Any]] = []
    errors: list[str] = []

    for url in SOURCE_URLS:
        try:
            all_events.extend(parse_url(url, date_set))
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    events = dedupe(all_events)
    write_schedule(events, target, errors)
    print(f"target_dates={target}, events={len(events)}, errors={len(errors)}")


if __name__ == "__main__":
    main()
