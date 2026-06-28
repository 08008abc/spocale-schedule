#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
スポカレ自動更新: ネットワーク調査版

目的:
- Playwrightでページを開いても本文に予定が出ないため、
  ページ裏で通信しているAPI候補URLを data/schedule.json の debug_info に出します。
- これは本番取得用ではなく、原因調査用です。

実行後、data/schedule.json の debug_info 内にある
api_candidates / date_response_candidates / request_urls_sample を確認してください。
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "schedule.json"
JST = ZoneInfo("Asia/Tokyo")

SOURCE_URLS = [
    "https://spocale.com/sports/1/team_and_players/92",
    "https://spocale.com/sports/18/leagues/556",
    "https://spocale.com/sports/14/team_and_players/4829",
    "https://spocale.com/sports/2/team_and_players/1315",
    "https://spocale.com/sports/3/team_and_players/258",
]

DATE_RE = re.compile(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}|20\d{2}\.\d{2}\.\d{2}\[[^\]]+\]")
SPORT_HINT_RE = re.compile(r"カブス|パドレス|BWF|カナダ|ネーションズリーグ|日本代表|シカゴ|MLB|試合|日程|schedule|event", re.I)


def wanted_dates():
    today = datetime.now(JST).date()
    return [today.isoformat(), (today + timedelta(days=1)).isoformat()]


def save(payload):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def run():
    debug_info = []
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1365, "height": 2200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        )

        for url in SOURCE_URLS:
            page = await context.new_page()

            request_urls = []
            response_summaries = []
            api_candidates = []
            date_response_candidates = []

            async def on_request(request):
                u = request.url
                request_urls.append(u)

            async def on_response(response):
                u = response.url
                status = response.status
                ctype = response.headers.get("content-type", "")

                if any(x in u.lower() for x in ["api", "schedule", "event", "match", "game", "team", "league", "calendar", "json"]):
                    api_candidates.append({"url": u, "status": status, "content_type": ctype[:80]})

                # 大きすぎる画像やフォントは読まない
                if any(x in ctype for x in ["image/", "font/", "video/", "audio/"]):
                    return

                try:
                    text = await response.text()
                except Exception:
                    return

                sample = text[:500].replace("\n", " ")
                has_date = bool(DATE_RE.search(text))
                has_hint = bool(SPORT_HINT_RE.search(text))

                if has_date or has_hint or "json" in ctype or "javascript" in ctype:
                    response_summaries.append({
                        "url": u,
                        "status": status,
                        "content_type": ctype[:80],
                        "has_date": has_date,
                        "has_sport_hint": has_hint,
                        "sample": sample,
                    })

                if has_date:
                    date_response_candidates.append({
                        "url": u,
                        "status": status,
                        "content_type": ctype[:80],
                        "sample": sample,
                    })

            page.on("request", on_request)
            page.on("response", on_response)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=25000)
                except Exception:
                    pass

                # 予定一覧が遅延読込・スクロール読込の場合に備える
                for _ in range(8):
                    await page.mouse.wheel(0, 1800)
                    await page.wait_for_timeout(1200)

                body_text = await page.locator("body").inner_text(timeout=10000)
                title = await page.title()

                debug_info.append({
                    "url": url,
                    "title": title,
                    "body_has_date": bool(DATE_RE.search(body_text)),
                    "body_sample": body_text[:1200].splitlines()[:80],
                    "api_candidates": api_candidates[:80],
                    "date_response_candidates": date_response_candidates[:20],
                    "response_summaries": response_summaries[:40],
                    "request_urls_sample": request_urls[:120],
                })

            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
            finally:
                await page.close()

        await browser.close()

    payload = {
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "timezone": "Asia/Tokyo",
        "source_name": "スポカレ",
        "target_dates": wanted_dates(),
        "events": [],
        "last_update_note": "ネットワーク調査版です。予定は更新せず、API候補URLをdebug_infoに出しています。",
        "last_update_errors": errors,
        "debug_info": debug_info,
    }
    save(payload)
    print(payload["last_update_note"])


if __name__ == "__main__":
    asyncio.run(run())
