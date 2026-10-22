"""Read current NBA season win totals from Kalshi's public market data.

Kalshi lists a ladder of markets for each team ("40+ wins", "45+ wins", ...). Each price is
the market's probability of reaching at least that many wins, so a team's line is where
the ladder crosses 50%, the same thing a sportsbook's over/under is set to.
"""
from __future__ import annotations

import json
import sys
import urllib.request

URL = ("https://api.elections.kalshi.com/trade-api/v2/events"
       "?series_ticker=KXNBAWINS&status=open&with_nested_markets=true&limit=200")
WIDE = 0.12  # a bid/ask gap wider than this is too thin to trust the midpoint


def _price(m):
    """Probability for one rung of the ladder: the midpoint when the market is tight."""
    bid = float(m.get("yes_bid_dollars") or 0)
    ask = float(m.get("yes_ask_dollars") or 1)
    last = m.get("last_price_dollars")
    if ask - bid <= WIDE or not last or float(last) <= 0:
        return (bid + ask) / 2
    return min(max(float(last), bid), ask)


def line_from_ladder(rungs):
    """The win total where P(wins >= k) crosses 50%, expressed like a sportsbook's x.5 line."""
    rungs = sorted(rungs)
    probs, low = [], 1.0
    for k, p in rungs:  # probabilities can't rise as the bar goes up
        low = min(low, p)
        probs.append((k, low))
    for (k1, p1), (k2, p2) in zip(probs, probs[1:]):
        if p1 >= 0.5 > p2:
            return round(k1 + (p1 - 0.5) / (p1 - p2) * (k2 - k1) - 0.5, 1)
    return None  # the ladder never crosses 50%; not enough information


def win_totals(season_year, teams):
    """{team: line} for every team whose ladder is informative. season_year is ESPN's (2027)."""
    req = urllib.request.Request(URL, headers={"User-Agent": "wl-draft-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        events = json.load(resp).get("events", [])
    prefix = str(season_year)[2:]
    out = {}
    for e in events:
        code = e["event_ticker"].split("-")[-1]  # e.g. 27OKC
        if not code.startswith(prefix) or code[len(prefix):] not in teams:
            continue
        rungs = [(m["floor_strike"], _price(m)) for m in e.get("markets", []) if m.get("floor_strike") is not None]
        line = line_from_ladder(rungs)
        if line is not None:
            out[code[len(prefix):]] = line
    return out


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    import wl

    lg = wl.League()
    lines = win_totals(lg.espn_season, set(lg.teams))
    print(f"{len(lines)} teams; sum {sum(lines.values()):.1f}")
    for t in lg.teams:
        now = lines.get(t)
        print(f"  {t}: market {now if now is not None else '  -- '}  preseason {lg.lines[t]}"
              + (f"  ({now - lg.lines[t]:+.1f})" if now is not None else ""))
