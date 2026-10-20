"""Refresh the W/L draft site's data from ESPN.

GitHub Actions runs this every 15 minutes during game hours. It keeps every game of the
season in data/season.json and the day-by-day title-odds history in data/history.json,
and writes what the page shows to site/data.json. A file is rewritten only when its
content changes, and the simulations are seeded from the results they use, so a run with
nothing new changes nothing.

Usage: python scripts/update_data.py [--full]
  --full  re-read all 30 team schedules now instead of once a day
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import numpy as np

import espn
import wl

SEASON_FILE = wl.DATA / "season.json"
HISTORY_FILE = wl.DATA / "history.json"
OUT = wl.ROOT / "site" / "data.json"
SIMS_HISTORY = 4000   # simulated seasons per finished day, for the odds history
SIMS_NOW = 12000      # simulated seasons for the current odds and tonight's leverage
SCHEDULE_REFRESH = timedelta(hours=20)
AHEAD_DAYS = 10
MODEL = {"priorGames": wl.PRIOR_GAMES, "homeEdge": wl.HOME_EDGE, "simsHistory": SIMS_HISTORY, "simsNow": SIMS_NOW}


def iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_text_if_changed(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def seed_for(*parts):
    """A simulation seed that changes only when its inputs do."""
    return int(hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16], 16)


def merge(games, g):
    old = games.get(g["id"])
    if old:
        if old["state"] == "final" and g["state"] in ("pre", "live"):
            return  # a stale feed; keep the result we already have
        if "spread" not in g and "spread" in old:
            g["spread"] = old["spread"]  # keep the last line we saw, which ends up the closing line
    games[g["id"]] = g


def refresh(lg, season, now, full):
    """Pull schedules and results into season; return ESPN's current US date."""
    games = season.setdefault("games", {})
    last = season.get("refreshed")
    if full or not last or now - datetime.fromisoformat(last.replace("Z", "+00:00")) > SCHEDULE_REFRESH:
        for t in lg.teams:
            for e in espn.team_schedule(lg.info[t]["espnId"], lg.espn_season).get("events", []):
                g = espn.parse_event(e, lg.by_espn)
                if g:
                    merge(games, g)
        season["refreshed"] = iso(now)
    today_et = now.astimezone(espn.ET).date()
    current = espn.scoreboard()
    for board in (espn.scoreboard(today_et - timedelta(days=1)), current):
        for e in board.get("events", []):
            g = espn.parse_event(e, lg.by_espn)
            if g:
                merge(games, g)
    return (current.get("day") or {}).get("date") or today_et.isoformat()


def build(lg, season, current_day):
    games = sorted((g for g in season["games"].values() if g["state"] != "off"), key=lambda g: (g["tip"], g["id"]))
    if not games:
        raise SystemExit("no games found; check the ESPN feed")
    today = date.fromisoformat(current_day)
    preseason = min(date.fromisoformat(g["day"]) for g in games) - timedelta(days=1)
    last = max(today, preseason)
    days = [(preseason + timedelta(days=i)).isoformat() for i in range((last - preseason).days + 1)]
    index = {d: i for i, d in enumerate(days)}
    nt = len(lg.teams)
    home_won = lambda g: g["score"][1] > g["score"][0]  # noqa: E731

    # The chart covers finished days: every day before the first one with games still to play.
    # Unplayed games more than a day old are stuck in the feed, so they don't hold it back.
    recent = (today - timedelta(days=1)).isoformat()
    pending = {g["day"] for g in games if g["state"] in ("pre", "live") and g["day"] >= recent}
    complete = 0
    for i, d in enumerate(days):
        if d in pending:
            break
        complete = i
    finals = [g for g in games if g["state"] == "final"]

    wins = np.zeros((complete + 1, nt), dtype=int)
    gp = np.zeros_like(wins)
    by_index = defaultdict(list)
    for g in finals:
        i = index.get(g["day"])
        if i is not None and i <= complete:
            by_index[i].append(g)
    for i in range(1, complete + 1):
        wins[i], gp[i] = wins[i - 1], gp[i - 1]
        for g in by_index[i]:
            a, h = lg.tidx[g["away"]], lg.tidx[g["home"]]
            gp[i, a] += 1
            gp[i, h] += 1
            wins[i, h if home_won(g) else a] += 1
    pts, vegas = lg.person_points(wins, gp)

    # Right now: every final so far, including tonight's.
    wins_now = np.zeros(nt, dtype=int)
    gp_now = np.zeros(nt, dtype=int)
    for g in finals:
        a, h = lg.tidx[g["away"]], lg.tidx[g["home"]]
        gp_now[a] += 1
        gp_now[h] += 1
        wins_now[h if home_won(g) else a] += 1
    pts_now = lg.person_points(wins_now[None, :], gp_now[None, :])[0][0]

    # Until December each team has only 80 games on the schedule; the last two depend on the
    # NBA Cup. Stand in an average opponent on a neutral court for every missing game.
    counts = Counter(t for g in games for t in (g["away"], g["home"]))
    phantoms = []
    for t in lg.teams:
        if counts[t] > wl.SEASON_GAMES:
            print(f"warning: {t} has {counts[t]} games scheduled", file=sys.stderr)
        phantoms += [(wl.AVG, t)] * max(wl.SEASON_GAMES - counts[t], 0)
    schedule = [(g["away"], g["home"]) for g in games] + phantoms
    prior = wl.calibrate(lg, schedule)
    a_all, b_all = lg.points_matrices(schedule)
    home_all, away_all, edge_all = lg.index_arrays(schedule)
    day_all = np.array([g["day"] for g in games] + ["9999-12-31"] * len(phantoms))

    # Title odds as they stood at the end of each finished day; computed once per day.
    history = read_json(HISTORY_FILE, {"model": MODEL, "odds": {}})
    if history.get("model") != MODEL:
        history = {"model": MODEL, "odds": {}}
    for i in range(complete + 1):
        d = days[i]
        if d in history["odds"]:
            continue
        rem = np.flatnonzero(day_all > d)
        alpha, beta = wl.posterior(lg, prior, wins[i], gp[i])
        rng = np.random.default_rng(seed_for("history", d, MODEL))
        totals, _ = wl.simulate(rng, pts[i], alpha, beta, home_all[rem], away_all[rem], edge_all[rem],
                                a_all[rem], b_all[rem], SIMS_HISTORY)
        history["odds"][d] = [round(float(x), 4) for x in wl.title_credit(totals).mean(axis=0)]

    # Odds right now. Tonight's games use their betting lines; leverage is how much one
    # game's result moves anybody's title odds.
    rem_idx = [k for k, g in enumerate(games) if g["state"] in ("pre", "live")] + list(range(len(games), len(schedule)))
    rem = np.array(rem_idx, dtype=int)
    fixed, slate_cols = {}, {}
    for col, k in enumerate(rem_idx):
        if k < len(games) and games[k]["day"] == current_day:
            slate_cols[games[k]["id"]] = col
            if "spread" in games[k]:
                fixed[col] = wl.spread_prob(games[k]["spread"])
    alpha, beta = wl.posterior(lg, prior, wins_now, gp_now)
    rng = np.random.default_rng(seed_for("now", current_day, [g["id"] for g in finals],
                                         sorted((games[k]["id"], games[k].get("spread")) for k in rem_idx if k < len(games)), MODEL))
    totals, home = wl.simulate(rng, pts_now, alpha, beta, home_all[rem], away_all[rem], edge_all[rem],
                               a_all[rem], b_all[rem], SIMS_NOW, fixed=fixed)
    credit = wl.title_credit(totals)
    leverage = {}
    for gid, col in slate_cols.items():
        mask = home[:, col]
        swing = np.abs(credit[mask].mean(axis=0) - credit[~mask].mean(axis=0)).max() if 0 < mask.sum() < len(mask) else 0.0
        leverage[gid] = round(float(swing) * 100, 1)

    slate = []
    for g in games:
        if g["day"] != current_day:
            continue
        item = {"id": g["id"], "away": g["away"], "home": g["home"], "tip": g["tip"], "state": g["state"]}
        if g["state"] == "final":
            item["score"] = g["score"]  # live scores come straight from ESPN in the browser
        if "spread" in g:
            item["spread"] = g["spread"]
        if g["id"] in leverage:
            item["leverage"] = leverage[g["id"]]
        slate.append(item)
    horizon = (today + timedelta(days=AHEAD_DAYS)).isoformat()

    teams = lg.teams_json()
    for t in teams:
        teams[t]["espn"] = lg.info[t]["espnAbbr"]
    data = {
        "meta": {
            "season": lg.draft["season"], "today": current_day, "model": MODEL,
            "linesSource": f"{lg.lines_doc['source']}, {lg.lines_doc['asOf']}",
        },
        "people": lg.people_json(),
        "teams": teams,
        "days": days,
        "games": [[index[g["day"]], g["away"], g["home"], g["home"] if home_won(g) else g["away"], g["id"]]
                  for g in finals if g["day"] in index],
        "slate": slate,
        "ahead": [[g["tip"], g["away"], g["home"]] for g in games if current_day < g["day"] <= horizon],
        "series": {
            "points": pts.astype(int).tolist(),
            "vegas": np.round(vegas, 2).tolist(),
            "odds": [history["odds"][d] for d in days[:complete + 1]],
            "rank": wl.ranks(pts).tolist(),
        },
        "oddsNow": [round(float(x), 4) for x in credit.mean(axis=0)],
        "projNow": [round(float(x), 1) for x in totals.mean(axis=0)],
        "bots": wl.vegas_bots(lg),
        "moments": wl.moments(lg, pts, {i: [(g["away"], g["home"]) for g in gs] for i, gs in by_index.items()}),
    }
    return data, history


def season_text(season):
    """One game per line, so the daily diffs stay readable."""
    rows = ",\n".join(f' "{k}": {json.dumps(season["games"][k], separators=(",", ":"))}' for k in sorted(season["games"]))
    return f'{{\n "refreshed": {json.dumps(season["refreshed"])},\n "games": {{\n{rows}\n }}\n}}\n'


def main():
    lg = wl.League()
    now = datetime.now(timezone.utc)
    season = read_json(SEASON_FILE, {"refreshed": None, "games": {}})
    current_day = refresh(lg, season, now, "--full" in sys.argv)
    data, history = build(lg, season, current_day)

    changed = []
    if write_text_if_changed(SEASON_FILE, season_text(season)):
        changed.append(SEASON_FILE.name)
    if write_text_if_changed(HISTORY_FILE, json.dumps(history, indent=1) + "\n"):
        changed.append(HISTORY_FILE.name)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    if read_json(OUT, {}).get("meta", {}).get("hash") != digest:
        data["meta"].update(updated=iso(now), hash=digest)
        write_text_if_changed(OUT, json.dumps(data, separators=(",", ":")) + "\n")
        changed.append(OUT.name)

    finals = len(data["games"])
    standings = sorted(zip(lg.people, data["oddsNow"]), key=lambda x: -x[1])
    print(f"ESPN day {current_day}: {finals} finals, chart through {data['days'][len(data['series']['points']) - 1]}")
    print("title odds:", ", ".join(f"{p} {o:.0%}" for p, o in standings))
    print("tonight:", ", ".join(f"{g['away']}@{g['home']} {g['state']}" + (f" lev {g['leverage']}" if "leverage" in g else "")
                                for g in data["slate"]) or "no games")
    print("changed:", ", ".join(changed) or "nothing")


if __name__ == "__main__":
    main()
