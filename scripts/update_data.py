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
import markets
import recap
import wl

SEASON_FILE = wl.DATA / "season.json"
HISTORY_FILE = wl.DATA / "history.json"
MARKET_FILE = wl.DATA / "market_lines.json"
OUT = wl.ROOT / "site" / "data.json"
SIMS_HISTORY = 4000   # simulated seasons per finished day, for the odds history
SIMS_NOW = 12000      # simulated seasons for the current odds and tonight's leverage
SCHEDULE_REFRESH = timedelta(hours=20)
MARKET_STALE = timedelta(days=3)  # older market lines than this aren't "current" any more
MARKET_HOUR = 5  # Eastern; by then the market has digested last night's games
AHEAD_DAYS = 10
MODEL = {"priorGames": wl.PRIOR_GAMES, "homeEdge": wl.HOME_EDGE, "simsHistory": SIMS_HISTORY, "simsNow": SIMS_NOW,
         "strengths": "morning market win totals when available, else preseason lines plus record"}


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


def refresh_market(lg, market, season, now):
    """Take one snapshot of the market's win totals per (Eastern) day, in the morning before
    that day's first tip, so a snapshot dated K prices the games from K on given every result
    through K-1."""
    et = now.astimezone(espn.ET)
    today = et.date().isoformat()
    if today in market["snapshots"] or et.hour < MARKET_HOUR:
        return
    tipped = iso(now)
    if any(g["state"] == "live" or (g["day"] == today and g["state"] != "off" and (g["state"] == "final" or g["tip"] <= tipped))
           for g in season["games"].values()):
        return  # today's games have started; tomorrow morning's snapshot will have them
    try:
        lines = markets.win_totals(lg.espn_season, set(lg.teams))
    except Exception as exc:  # the market being down shouldn't stop the standings
        print(f"market lines unavailable: {exc}", file=sys.stderr)
        return
    if len(lines) == len(lg.teams):
        market["snapshots"][today] = dict(sorted(lines.items()))
    else:
        print(f"market lines incomplete ({len(lines)} teams); skipping", file=sys.stderr)


def build(lg, season, current_day, market):
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
    played = lg.person_games(gp)  # the standings rank by points per game played

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

    # Team strengths for simulating what's left. With market win totals from that time, the
    # market sets them (it already knows the records, injuries and trades); otherwise the
    # calibrated preseason lines are blended with the records.
    snapshots = market["snapshots"]

    def lines_as_of(day_iso):
        taken = [d for d in snapshots if d <= day_iso]
        return (max(taken), snapshots[max(taken)]) if taken else (None, None)

    def strength_params(win_row, gp_row, lines_day, lines):
        if lines is None:
            return wl.posterior(lg, prior, win_row, gp_row)
        # The snapshot priced the games from its morning on, given the records through the night
        # before. Fit to that, so results since then still count when the rest is simulated.
        wins_then = np.zeros(nt, dtype=int)
        for g in finals:
            if g["day"] < lines_day:
                wins_then[lg.tidx[g["home"] if home_won(g) else g["away"]]] += 1
        rates = wl.market_strengths(lg, [schedule[c] for c in np.flatnonzero(day_all >= lines_day)], lines, wins_then)
        p = np.array([rates[t] for t in lg.teams])
        k = wl.PRIOR_GAMES + gp_row  # the market is at least as sure as preseason line plus record
        return k * p, k * (1 - p)

    # Title odds as they stood at the end of each finished day; computed once per day, with
    # the market lines available by the next morning.
    history = read_json(HISTORY_FILE, {"model": MODEL, "odds": {}})
    if history.get("model") != MODEL:
        history = {"model": MODEL, "odds": {}}
    for i in range(complete + 1):
        d = days[i]
        if d in history["odds"]:
            continue
        rem = np.flatnonzero(day_all > d)
        alpha, beta = strength_params(wins[i], gp[i], *lines_as_of((date.fromisoformat(d) + timedelta(days=1)).isoformat()))
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
    lines_day, lines_now = lines_as_of(current_day)
    if lines_day and date.fromisoformat(lines_day) < today - MARKET_STALE:
        lines_day, lines_now = None, None
    alpha, beta = strength_params(wins_now, gp_now, lines_day, lines_now)
    rng = np.random.default_rng(seed_for("now", current_day, [g["id"] for g in finals], lines_day,
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

    # The recap covers the latest finished day that had games.
    ranks = wl.ranks(pts, played)
    leads = {i: s for i, s in wl.lead_changes(pts, played)}
    day_recap = None
    last = max((i for i in by_index if i <= complete), default=0)
    if last >= 1:
        took = leads.get(last)
        led_before = any(s == took for i, s in leads.items() if i < last)
        por_w, por_gp = int(wins[last, lg.tidx["POR"]]), int(gp[last, lg.tidx["POR"]])
        day_recap = recap.build(
            lg, days[last], [g for g in by_index[last] if g.get("score")], pts[last] - pts[last - 1],
            ranks[last - 1], ranks[last], history["odds"].get(days[last - 1]), history["odds"][days[last]],
            (took, led_before) if took is not None else None, (por_w, por_gp - por_w))

    teams = lg.teams_json()
    for t in teams:
        teams[t]["espn"] = lg.info[t]["espnAbbr"]
    data = {
        "meta": {
            "season": lg.draft["season"], "today": current_day, "model": MODEL,
            "linesSource": f"{lg.lines_doc['source']}, {lg.lines_doc['asOf']}",
            "oddsBasis": "market" if lines_now else "model",
        },
        "market": {"source": market["source"], "asOf": lines_day, "lines": lines_now} if lines_now else None,
        "recap": day_recap,
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
            "rank": ranks.tolist(),
            "pct": [[round(p / g, 3) if g else None for p, g in zip(p_row, g_row)]
                    for p_row, g_row in zip(pts.tolist(), played.tolist())],
        },
        "oddsNow": [round(float(x), 4) for x in credit.mean(axis=0)],
        "projNow": [round(float(x), 1) for x in totals.mean(axis=0)],
        "bots": wl.vegas_bots(lg),
        "moments": wl.moments(lg, pts, {i: [(g["away"], g["home"]) for g in gs] for i, gs in by_index.items()}, played),
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
    market = read_json(MARKET_FILE, {"source": "Kalshi win-total markets (KXNBAWINS), each team's 50% point",
                                     "snapshots": {}})
    refresh_market(lg, market, season, now)
    data, history = build(lg, season, current_day, market)

    changed = []
    if write_text_if_changed(SEASON_FILE, season_text(season)):
        changed.append(SEASON_FILE.name)
    if write_text_if_changed(MARKET_FILE, json.dumps(market, indent=1) + "\n"):
        changed.append(MARKET_FILE.name)
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
