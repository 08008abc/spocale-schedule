#!/usr/bin/env python3
"""
スポカレ 今日＋明日 自動更新・登録対象フィルター版

方針:
- ページ上の /game/ リンクを日付ごとに拾う
- team_and_players ページでは、登録チーム/選手に関係する試合だけ残す
- sports / leagues ページでは、そのURL自体が登録対象なので大会予定として残す
- 各 game 詳細ページから TV放送情報 / 配信情報 を読む
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
BASE = "https://spocale.com"
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

# URLごとの強めの別名。ここに入っている文字を試合行に含むものだけ残す。
TEAM_ALIASES = {
    "https://spocale.com/sports/14/team_and_players/871": ["ヴィクトリーナ", "姫路"],
    "https://spocale.com/sports/2/team_and_players/1315": ["INAC", "神戸レオネッサ", "INAC神戸"],
    "https://spocale.com/sports/3/team_and_players/258": ["コベルコ", "スティーラーズ", "神戸S", "神戸"],
    "https://spocale.com/sports/2/team_and_players/53": ["ツエーゲン", "金沢"],
    "https://spocale.com/sports/2/team_and_players/2596": ["ASハリマ", "ハリマ"],
    "https://spocale.com/sports/1/team_and_players/92": ["カブス"],
    "https://spocale.com/sports/1/team_and_players/3418": ["報徳"],
    "https://spocale.com/sports/1/team_and_players/7731": ["神戸国際"],
    "https://spocale.com/sports/1/team_and_players/7776": ["東洋大姫路", "東洋"],
    "https://spocale.com/sports/1/team_and_players/2280": ["星稜"],
    "https://spocale.com/sports/1/team_and_players/2279": ["日本航空石川", "航空石川"],
    "https://spocale.com/sports/2/team_and_players/3815": ["ヴィッセル神戸U-18", "神戸U-18"],
    "https://spocale.com/sports/14/team_and_players/4829": ["日本"],
    "https://spocale.com/sports/14/team_and_players/3588": ["日本"],
    "https://spocale.com/sports/2/team_and_players/269": ["日本"],
    "https://spocale.com/sports/2/team_and_players/437": ["イタリア"],
    "https://spocale.com/sports/2/team_and_players/2615": ["なでしこ", "日本"],
    "https://spocale.com/sports/5/team_and_players/519": ["日本"],
    "https://spocale.com/sports/5/team_and_players/3013": ["日本"],
    "https://spocale.com/sports/3/team_and_players/3684": ["日本"],
    "https://spocale.com/sports/3/team_and_players/22376": ["日本"],
    "https://spocale.com/sports/1/team_and_players/1316": ["侍ジャパン", "日本"],
    "https://spocale.com/sports/43/team_and_players/1216": ["日本"],
    "https://spocale.com/sports/2/team_and_players/335": ["ミラン"],
    "https://spocale.com/sports/2/team_and_players/22": ["ヴィッセル", "神戸"],
    "https://spocale.com/sports/5/team_and_players/121": ["ストークス", "神戸"],
}

NOISE = {
    "LIVE", "見逃し", "録画", "通知設定", "この試合を通知する", "関連カレンダー",
    "無料ダウンロード", "SEARCH", "MENU", "SCROLL TO TOP",
}


def now_jst() -> datetime:
    return datetime.now(JST)


def target_dates() -> list[str]:
    today = now_jst().date()
    return [today.isoformat(), (today + timedelta(days=1)).isoformat()]


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def fetch(url: str) -> str:
    last = None
    for i in range(3):
        try:
            r = requests.get(
                url,
                timeout=25,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; spocale-schedule/5.0)",
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


def is_team_page(url: str) -> bool:
    return "/team_and_players/" in url


def sport_from_url(url: str) -> str:
    m = re.search(r"/sports/(\d+)", url)
    return SPORT_BY_ID.get(m.group(1), "記載なし") if m else "記載なし"


def page_name(soup: BeautifulSoup) -> str:
    for selector in ["h1", "h2", "title"]:
        node = soup.select_one(selector)
        if node:
            t = clean(node.get_text(" ", strip=True)).replace(" | スポカレ", "")
            if t and "スポーツ日程更新中" not in t:
                return t
    return "記載なし"


def iso_date(text: str) -> str | None:
    m = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def normalize_time(text: str) -> str:
    m = re.search(r"(\d{1,2}:\d{2}|未定|終日)", text)
    if not m:
        return "記載なし"
    t = m.group(1)
    if re.match(r"^\d{1,2}:\d{2}$", t):
        h, mm = t.split(":")
        return f"{int(h):02d}:{mm}"
    return t


def should_stop_listing(text: str) -> bool:
    if text in {"SEARCH", "MENU", "SCROLL TO TOP"}:
        return True
    if text.startswith("#### SEARCH") or text.startswith("#### MENU"):
        return True
    if text == "過去の試合日程":
        return True
    return False


def game_items_by_dom(soup: BeautifulSoup, dates: set[str]) -> list[dict[str, str]]:
    """
    DOM順で直前の日付を /game/ リンクに付ける。
    ただし SEARCH / MENU 以降は停止。
    """
    current_date: str | None = None
    items: list[dict[str, str]] = []

    for node in soup.find_all(["h1", "h2", "h3", "h4", "div", "p", "li", "span", "a"]):
        text = clean(node.get_text(" ", strip=True))
        if not text:
            continue

        if should_stop_listing(text) and current_date is not None:
            break

        d = iso_date(text)
        if d:
            current_date = d

        if node.name != "a":
            continue

        href = node.get("href") or ""
        if "/game/" not in href:
            continue

        if not current_date or current_date not in dates:
            continue

        entry = text
        if not re.search(r"(\d{1,2}:\d{2}|未定|終日)", entry):
            continue

        items.append({
            "date": current_date,
            "entry": entry,
            "game_url": urljoin(BASE, href),
        })

    return items


def aliases_for_url(url: str, title: str) -> list[str]:
    aliases = TEAM_ALIASES.get(url, []).copy()

    # タイトル由来の保険
    t = title
    for word in ["の日程一覧", "日程一覧", "代表", "男子", "女子", "U-18"]:
        t = t.replace(word, "")
    t = clean(t)
    if t and t not in aliases and len(t) >= 2:
        aliases.append(t)

    return [a for a in aliases if a]


def keep_for_registered_url(source_url: str, title: str, entry: str) -> bool:
    if not is_team_page(source_url):
        return True

    aliases = aliases_for_url(source_url, title)
    if not aliases:
        return True

    return any(alias in entry for alias in aliases)


def parse_title(title: str, source_url: str) -> tuple[str, str]:
    title = clean(title).replace(" | スポカレ", "")
    title = re.sub(r"\s*日時・.*?情報\s*", " ", title)
    title = clean(title)

    if " vs " not in title:
        return title or "記載なし", "大会のみ"

    before, after = title.split(" vs ", 1)
    parts = before.split(" ")
    if len(parts) >= 2:
        event = " ".join(parts[:-1])
        home = parts[-1]
        target = f"{home} vs {after}"
    else:
        event = "記載なし"
        target = title

    return clean(event), clean(target)


def parse_entry(entry: str, source_url: str, page_title: str) -> dict[str, str]:
    sport = sport_from_url(source_url)
    time_value = normalize_time(entry)

    text = clean(entry)
    text = re.sub(r"^(\d{1,2}:\d{2}|未定|終日)\s*", "", text)
    if sport != "記載なし":
        text = re.sub(rf"^{re.escape(sport)}\s*", "", text)

    text = re.sub(r"\s+VS\s+(\d{1,2}:\d{2}|未定|終日)\s+", " vs ", text)
    text = text.replace(" VS ", " vs ")

    left, right = (text.split("|", 1) + [""])[:2] if "|" in text else (text, "")

    if is_team_page(source_url):
        event, target = parse_title(left, source_url)
        kind = "試合"
    else:
        event = clean(left) or page_title
        target = "大会のみ"
        kind = "大会"

    venue = "記載なし"
    if right:
        d = clean(right)
        for token in [event, target, page_title]:
            if token and token != "記載なし":
                d = clean(d.replace(token, " "))
        parts = d.split(" ")
        if len(parts) >= 2 and len(parts) % 2 == 0 and parts[: len(parts)//2] == parts[len(parts)//2 :]:
            d = " ".join(parts[: len(parts)//2])
        venue = d or "記載なし"

    return {
        "time": time_value,
        "type": kind,
        "sport": sport,
        "event": event or "記載なし",
        "target": target or "記載なし",
        "venue": venue,
    }


def detail_text_lines(game_url: str) -> list[str]:
    html = fetch(game_url)
    soup = BeautifulSoup(html, "html.parser")
    return [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]


def provider_section(lines: list[str], start: str, stops: list[str]) -> str:
    active = False
    providers: list[str] = []

    for line in lines:
        if start in line:
            active = True
            continue

        if active and any(s in line for s in stops):
            break

        if not active:
            continue

        if not line or line in NOISE:
            continue
        if re.match(r"^\d{1,2}:\d{2}\s*~", line):
            continue
        if "通知" in line or "カレンダー" in line or "関連" in line:
            continue

        line = line.replace("LIVE", "").replace("見逃し", "").replace("録画", "")
        line = clean(line)
        if line and line not in NOISE:
            providers.append(line)

    return "、".join(dict.fromkeys(providers)) if providers else "記載なし"


def media_from_detail(game_url: str) -> tuple[str, str]:
    try:
        lines = detail_text_lines(game_url)
        tv = provider_section(lines, "TV放送情報", ["配信情報", "関連カレンダー", "SEARCH", "MENU"])
        stream = provider_section(lines, "配信情報", ["関連カレンダー", "SEARCH", "MENU"])
        return tv, stream
    except Exception:
        return "記載なし", "記載なし"


def parse_source(source_url: str, dates: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    html = fetch(source_url)
    soup = BeautifulSoup(html, "html.parser")
    title = page_name(soup)

    raw_items = game_items_by_dom(soup, dates)
    events: list[dict[str, Any]] = []
    errors: list[str] = []

    for item in raw_items:
        if not keep_for_registered_url(source_url, title, item["entry"]):
            continue

        base = parse_entry(item["entry"], source_url, title)
        tv, stream = media_from_detail(item["game_url"])

        events.append({
            "date": item["date"],
            "time": base["time"],
            "type": base["type"],
            "sport": base["sport"],
            "event": base["event"],
            "target": base["target"],
            "venue": base["venue"],
            "tv": tv,
            "stream": stream,
            "source": source_url,
            "game_url": item["game_url"],
        })

    return events, errors


def tkey(t: str) -> int:
    if re.match(r"^\d{2}:\d{2}$", t or ""):
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    if t == "終日":
        return 9997
    if t == "未定":
        return 9998
    return 9999


def dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for e in events:
        key = (e["date"], e["time"], e["type"], e["sport"], e["target"])
        if key not in out:
            out[key] = e
        else:
            old = out[key]
            for field in ["event", "venue", "tv", "stream", "game_url"]:
                if old.get(field) in {"記載なし", "", None} and e.get(field) not in {"記載なし", "", None}:
                    old[field] = e[field]
    return sorted(out.values(), key=lambda e: (e["date"], tkey(e["time"]), e["sport"], e["target"]))


def write_payload(events: list[dict[str, Any]], target: list[str], errors: list[str]) -> None:
    payload = {
        "generated_at": now_jst().isoformat(timespec="seconds"),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "source_urls": SOURCE_URLS,
        "display_rule": "毎日0時に日本時間の実行日当日と翌日の2日分へ更新",
        "target_dates": target,
        "events": events,
        "last_update_note": f"{target[0]} と {target[1]} の登録対象予定を {len(events)} 件取得しました。",
        "last_update_errors": errors[:100],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    target = target_dates()
    dates = set(target)
    all_events: list[dict[str, Any]] = []
    errors: list[str] = []

    for source_url in SOURCE_URLS:
        try:
            ev, er = parse_source(source_url, dates)
            all_events.extend(ev)
            errors.extend(er)
        except Exception as exc:
            errors.append(f"{source_url}: {type(exc).__name__}: {exc}")

    events = dedupe(all_events)
    write_payload(events, target, errors)
    print(f"updated target_dates={target}, events={len(events)}, errors={len(errors)}")


if __name__ == "__main__":
    main()
