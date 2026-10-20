"""Read NBA schedules, scores and betting lines from ESPN's public site API.

The API is free and needs no key. It is also unofficial, so parsing is defensive: a game
that doesn't look like a counted regular-season game is skipped instead of stopping the run.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ET = ZoneInfo("America/New_York")  # ESPN's game dates are US Eastern dates
HEADERS = {"User-Agent": "wl-draft-tracker/1.0", "Accept-Encoding": "gzip"}
REGULAR_SEASON = 2
OFF = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_SUSPENDED", "STATUS_FORFEIT"}


def get_json(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            return json.loads(body)
        except Exception as exc:  # timeouts and 5xx happen; retry a couple of times
            if attempt == tries - 1:
                raise
            print(f"retrying {url}: {exc}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))


def team_schedule(espn_id, season_year):
    return get_json(f"{BASE}/teams/{espn_id}/schedule?season={season_year}&seasontype={REGULAR_SEASON}")


def scoreboard(day=None):
    """ESPN's scoreboard for a US date, or for ESPN's current day when day is None."""
    return get_json(f"{BASE}/scoreboard" + (f"?dates={day:%Y%m%d}" if day else ""))


def _score(competitor):
    s = competitor.get("score")
    if isinstance(s, dict):
        s = s.get("value", s.get("displayValue"))
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _cup_final(comp):
    """The NBA Cup championship game doesn't count in the standings; its semifinals do."""
    text = " ".join([n.get("headline", "") for n in comp.get("notes", [])] + [(comp.get("type") or {}).get("text", "")]).lower()
    return "cup" in text and ("championship" in text or re.search(r"(?<![a-z-])finals?\b", text) is not None)


def parse_event(event, by_espn):
    """One ESPN event as a game dict, or None when it doesn't count toward the standings."""
    comp = event["competitions"][0]
    season_type = (event.get("seasonType") or {}).get("type") or (event.get("season") or {}).get("type")
    if season_type is not None and int(season_type) != REGULAR_SEASON:
        return None
    if _cup_final(comp):
        print(f"skipping NBA Cup final {event.get('id')}", file=sys.stderr)
        return None
    sides = {}
    for c in comp.get("competitors", []):
        team = by_espn.get(c["team"]["abbreviation"])
        if team is None:
            return None
        sides[c["homeAway"]] = (team, _score(c))
    if set(sides) != {"home", "away"}:
        return None

    status = comp["status"]
    kind = status["type"]
    if kind.get("name") in OFF:
        state = "off"
    elif kind.get("completed"):
        state = "final"
    elif kind.get("state") == "in":
        state = "live"
    else:
        state = "pre"
    tip = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    game = {
        "id": str(event["id"]),
        "tip": tip.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "day": tip.astimezone(ET).date().isoformat(),
        "away": sides["away"][0],
        "home": sides["home"][0],
        "state": state,
    }
    if state in ("final", "live") and None not in (sides["away"][1], sides["home"][1]):
        game["score"] = [sides["away"][1], sides["home"][1]]
    if state == "final" and "score" not in game:
        game["state"] = "pre"  # marked complete without a score; wait for the score
    odds = (comp.get("odds") or [None])[0]
    if odds and odds.get("spread") is not None:
        try:
            game["spread"] = float(odds["spread"])  # the home team's line; negative means favored
        except (TypeError, ValueError):
            pass
    return game
