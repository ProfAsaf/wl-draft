"""Generate a coherent sample season for the W/L draft mockup.

The sample runs from Oct 20, 2026 through Jan 13, 2027, when every team has played 40
games, and freezes "now" at 8:15 PM ET on Thu Jan 14 with two games live. Final records,
the Christmas Day slate and the Jan 13 slate are pinned so the mockup matches the design
sketches. Everything else is random but consistent: each game has one winner, and each
team's results add up to its record.

Title odds use the same model as the live site (scripts/wl.py).

Writes mockup/sample-data.js, which sets window.SAMPLE_DATA.
Usage: python scripts/make_sample_data.py [seed]
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timedelta, timezone

import numpy as np

import wl

OUT = wl.ROOT / "mockup" / "sample-data.js"

SEASON_START = date(2026, 10, 20)  # day 0
LAST_PLAYED_DAY = 85               # Jan 13, 2027
TODAY_DAY = 86                     # Jan 14, 2027
NOW = "2027-01-15T01:15:00Z"       # 8:15 PM ET on Jan 14
GP = 40                            # games every team has played by Jan 13

SIMS_HISTORY = 3000   # simulated seasons per day for the title-odds history
SIMS_TONIGHT = 12000  # simulated seasons for tonight's numbers

# Wins at Jan 13 (40 games each), chosen so the mockup matches the design sketches.
RECORDS = {
    "ATL": 21, "BOS": 26, "BKN": 15, "CHA": 18, "CHI": 13, "CLE": 22, "DAL": 15, "DEN": 25,
    "DET": 23, "GSW": 18, "HOU": 25, "IND": 23, "LAC": 13, "LAL": 23, "MEM": 13, "MIA": 23,
    "MIL": 14, "MIN": 22, "NOP": 13, "NYK": 23, "OKC": 31, "ORL": 23, "PHI": 24, "PHX": 19,
    "POR": 18, "SAS": 30, "SAC": 12, "TOR": 24, "UTA": 15, "WAS": 16,
}

# (away, home, winner)
CHRISTMAS = [("CLE", "NYK", "CLE"), ("DEN", "LAL", "DEN"), ("PHX", "GSW", "GSW"),
             ("OKC", "SAS", "OKC"), ("BOS", "PHI", "BOS")]
JAN13 = [("UTA", "OKC", "OKC"), ("CHA", "BOS", "BOS"), ("MEM", "HOU", "HOU"),
         ("NOP", "TOR", "TOR"), ("GSW", "SAC", "SAC"), ("LAC", "SAS", "SAS")]
CHRISTMAS_DAY, JAN13_DAY = 66, 85

# Tonight. Live games carry the clock and score at NOW; `final` scripts the demo.
TONIGHT = [
    dict(away="PHI", home="NYK", tip="2027-01-15T00:00:00Z", status="live", clock="Q3 4:12",
         left=16.2, score=[84, 88], fav="NYK", spread=4.5, final=[104, 112]),
    dict(away="SAC", home="BKN", tip="2027-01-15T00:30:00Z", status="live", clock="Q2 1:30",
         left=25.5, score=[49, 51], fav="BKN", spread=2.5, final=[108, 101]),
    dict(away="POR", home="MIL", tip="2027-01-15T01:30:00Z", status="pre", fav="MIL", spread=3.5,
         final=[103, 110]),
    dict(away="HOU", home="MEM", tip="2027-01-15T01:30:00Z", status="pre", fav="HOU", spread=2.5,
         final=[117, 99]),
    dict(away="UTA", home="GSW", tip="2027-01-15T03:00:00Z", status="pre", fav="GSW", spread=6.5,
         final=[115, 111]),
    dict(away="DEN", home="LAC", tip="2027-01-15T03:30:00Z", status="pre", fav="DEN", spread=4.5,
         final=[121, 106]),
]
DEMO_ORDER = [0, 1, 3, 2, 4, 5]  # the order tonight's games go final in the demo

TIP_SLOTS_UTC = ["00:00", "00:30", "01:00", "02:00", "03:00", "03:30"]  # 7 PM to 10:30 PM ET

LG = wl.League()
TEAMS, TIDX, PEOPLE, NP = LG.teams, LG.tidx, LG.people, LG.n

assert sum(RECORDS.values()) == len(TEAMS) * GP // 2, "wins must equal losses"


def make_blocks(rng):
    """Day blocks; each block holds one round in which every team plays once."""
    head = [2] * 24 + [3] * 6
    rng.shuffle(head)
    played, d = [], 0
    for n in head:
        played.append(list(range(d, d + n)))
        d += n
    played.append([CHRISTMAS_DAY, CHRISTMAS_DAY + 1])
    d = CHRISTMAS_DAY + 2
    for _ in range(8):
        played.append([d, d + 1])
        d += 2
    played.append([JAN13_DAY - 1, JAN13_DAY])
    assert len(played) == GP and d == JAN13_DAY - 1

    future = [[TODAY_DAY, TODAY_DAY + 1]]
    tail = [2] * 37 + [3] * 4
    rng.shuffle(tail)
    d = TODAY_DAY + 2
    for n in tail:
        future.append(list(range(d, d + n)))
        d += n
    assert len(future) == wl.SEASON_GAMES - GP and d == 174
    return played, future


def make_round(rng, block, home_count, locked=(), locked_day=None):
    """(day, away, home) for one round; locked games go on locked_day, the rest elsewhere.

    The team with fewer home games so far hosts, so everyone ends near 41 home games.
    """
    games, used = [], set()
    for away, home in locked:
        games.append((locked_day, away, home))
        used |= {away, home}
        home_count[home] += 1
    rest = [t for t in TEAMS if t not in used]
    rng.shuffle(rest)
    days = [d for d in block if d != locked_day]
    for i in range(0, len(rest), 2):
        a, b = rest[i], rest[i + 1]
        if home_count[a] == home_count[b]:
            home = a if rng.random() < 0.5 else b
        else:
            home = a if home_count[a] < home_count[b] else b
        away = b if home == a else a
        home_count[home] += 1
        games.append((rng.choice(days), away, home))
    return games


def make_schedule(rng):
    played_blocks, future_blocks = make_blocks(rng)
    home_count = Counter()
    played, locked = [], {}
    for block in played_blocks:
        if block[0] == CHRISTMAS_DAY:
            slate = CHRISTMAS
        elif block[-1] == JAN13_DAY:
            slate = JAN13
        else:
            slate = ()
        start = len(played)
        locked_day = block[0] if slate is CHRISTMAS else block[-1]
        played += make_round(rng, block, home_count, [(a, h) for a, h, _ in slate], locked_day)
        for k, (_, _, w) in enumerate(slate):
            locked[start + k] = w
    future = []
    for i, block in enumerate(future_blocks):
        slate = [(g["away"], g["home"]) for g in TONIGHT] if i == 0 else ()
        future += make_round(rng, block, home_count, slate, TODAY_DAY if i == 0 else None)
    return played, locked, future


def orient(rng, games, locked):
    """Pick winners so every team ends exactly on its record; locked games keep theirs."""
    winners = []
    for g, (_, away, home) in enumerate(games):
        if g in locked:
            winners.append(locked[g])
        else:
            winners.append(home if rng.random() < wl.home_prob(LG.p0[home], LG.p0[away]) else away)
    while True:
        wins = Counter(winners)
        excess = {t: wins[t] - RECORDS[t] for t in TEAMS}
        over = [t for t in TEAMS if excess[t] > 0]
        if not over:
            return winners
        beat = defaultdict(list)  # winner -> [(game, loser)] over games that may flip
        for g, (_, away, home) in enumerate(games):
            if g not in locked:
                w = winners[g]
                beat[w].append((g, home if w == away else away))
        for edges in beat.values():
            rng.shuffle(edges)
        start = rng.choice(over)
        prev, queue, end = {start: None}, deque([start]), None
        while queue:
            u = queue.popleft()
            if excess[u] < 0:
                end = u
                break
            for g, v in beat[u]:
                if v not in prev:
                    prev[v] = (u, g)
                    queue.append(v)
        if end is None:
            raise RuntimeError("records cannot be met with this schedule")
        v = end
        while prev[v] is not None:  # flipping each game on the path moves one win along it
            u, g = prev[v]
            winners[g] = v
            v = u


def series_from(played, winners):
    """Cumulative team wins and games after each day; index 0 is preseason."""
    n = LAST_PLAYED_DAY + 2
    wins = np.zeros((n, len(TEAMS)), dtype=int)
    gp = np.zeros((n, len(TEAMS)), dtype=int)
    by_day = defaultdict(list)
    for (day, away, home), w in zip(played, winners):
        by_day[day].append((away, home, w))
    for i in range(1, n):
        wins[i], gp[i] = wins[i - 1], gp[i - 1]
        for away, home, w in by_day[i - 1]:
            gp[i, TIDX[away]] += 1
            gp[i, TIDX[home]] += 1
            wins[i, TIDX[w]] += 1
    return wins, gp


def longest_streaks(played, winners):
    runs = {t: [0, 0, 0, 0] for t in TEAMS}  # current W, current L, best W, best L
    for (_, away, home), w in zip(played, winners):
        for t in (away, home):
            r = runs[t]
            if t == w:
                r[0], r[1] = r[0] + 1, 0
            else:
                r[0], r[1] = 0, r[1] + 1
            r[2], r[3] = max(r[2], r[0]), max(r[3], r[1])
    return max(max(r[2], r[3]) for r in runs.values())


def storyline_ok(pts, played, winners):
    changes = wl.lead_changes(pts)
    leaders = {s for _, s in changes}
    brian = PEOPLE.index("Brian")
    brian_early = any(s == brian and i < 75 for i, s in changes)
    return (5 <= len(changes) <= 9 and len(leaders) >= 4 and brian_early
            and changes[0][0] > 3 and longest_streaks(played, winners) <= 11)


def build(seed):
    rng = random.Random(seed)
    played, locked, future = make_schedule(rng)
    winners = orient(rng, played, locked)
    order = sorted(range(len(played)), key=lambda g: played[g][0])  # chronological from here on
    played, winners = [played[g] for g in order], [winners[g] for g in order]
    wins, gp = series_from(played, winners)
    pts, vegas = LG.person_points(wins, gp)
    return rng, played, winners, future, wins, gp, pts, vegas


def pick_seed(start):
    for seed in range(start, start + 400):
        _, played, winners, _, _, _, pts, _ = build(seed)
        if storyline_ok(pts, played, winners):
            return seed
    raise RuntimeError("no seed produced a good storyline")


def tonight_prob(g):
    """Home win probability for one of tonight's games from its spread, score and clock."""
    home_spread = -g["spread"] if g["fav"] == g["home"] else g["spread"]
    if g["status"] != "live":
        return wl.spread_prob(home_spread)
    return wl.spread_prob(home_spread, g["score"][1] - g["score"][0], g["left"])


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else pick_seed(1)
    rng, played, winners, future, wins, gp, pts, vegas = build(seed)
    nprng = np.random.default_rng(seed)
    n_hist = LAST_PLAYED_DAY + 2

    # Sketch numbers this sample has to reproduce.
    final = {PEOPLE[s]: int(pts[-1, s]) for s in range(NP)}
    assert final == {"Ryan": 147, "Brian": 152, "Matt": 149, "Nick": 138, "Asaf": 143}, final
    assert [int(x) for x in pts[-1] - pts[-2]] == [3, 4, 0, 1, 2]
    assert all(int(gp[-1, TIDX[t]]) == GP and int(wins[-1, TIDX[t]]) == RECORDS[t] for t in TEAMS)

    # Title odds history: simulate everything after each day with that day's strengths.
    all_games = played + future
    pairs = [(a, h) for _, a, h in all_games]
    prior = wl.calibrate(LG, pairs)
    a_all, b_all = LG.points_matrices(pairs)
    home_all, away_all, edge_all = LG.index_arrays(pairs)
    days_all = np.array([g[0] for g in all_games])
    p_pre = np.array([wl.home_prob(prior[h], prior[a]) for a, h in pairs])
    print("model preseason projection:", dict(zip(PEOPLE, np.round(p_pre @ a_all + (1 - p_pre) @ b_all, 1))))
    odds = np.zeros((n_hist, NP))
    for i in range(n_hist):
        rem = np.flatnonzero(days_all > i - 1)  # games on days <= i - 1 are done
        alpha, beta = wl.posterior(LG, prior, wins[i], gp[i])
        totals, _ = wl.simulate(nprng, pts[i], alpha, beta, home_all[rem], away_all[rem], edge_all[rem],
                                a_all[rem], b_all[rem], SIMS_HISTORY)
        odds[i] = wl.title_credit(totals).mean(axis=0)

    # Tonight: live and pregame probabilities, leverage, and odds after each demo final.
    rem = np.flatnonzero(days_all > LAST_PLAYED_DAY)
    tonight_pos = {}
    for k, g in enumerate(rem):
        day, away, home = all_games[g]
        if day == TODAY_DAY:
            tonight_pos[next(j for j, t in enumerate(TONIGHT) if (t["away"], t["home"]) == (away, home))] = k
    fixed = {tonight_pos[j]: tonight_prob(g) for j, g in enumerate(TONIGHT)}
    alpha, beta = wl.posterior(LG, prior, wins[-1], gp[-1])
    args = (alpha, beta, home_all[rem], away_all[rem], edge_all[rem], a_all[rem], b_all[rem], SIMS_TONIGHT)
    totals, home = wl.simulate(nprng, pts[-1], *args, fixed=fixed)
    credit = wl.title_credit(totals)
    odds_now = credit.mean(axis=0)
    proj_now = totals.mean(axis=0)
    for j, g in enumerate(TONIGHT):
        k = tonight_pos[j]
        mask = home[:, k]
        swing = np.abs(credit[mask].mean(axis=0) - credit[~mask].mean(axis=0))
        g["leverage"] = round(float(swing.max()) * 100, 1)
        g["winProb"] = round(fixed[k], 3)
    odds_demo = []
    for j in DEMO_ORDER:
        g = TONIGHT[j]
        fixed[tonight_pos[j]] = 1.0 if g["final"][1] > g["final"][0] else 0.0
        t2, _ = wl.simulate(nprng, pts[-1], *args, fixed=fixed)
        odds_demo.append([round(float(x), 4) for x in wl.title_credit(t2).mean(axis=0)])

    # Schedule ahead (tonight is listed separately) so each team's next games are known.
    ahead = []
    for day, away, home in sorted(future):
        if TODAY_DAY < day <= TODAY_DAY + 10:
            d = SEASON_START + timedelta(days=day + 1)
            hh, mm = rng.choice(TIP_SLOTS_UTC).split(":")
            tip = datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=timezone.utc)
            ahead.append([tip.strftime("%Y-%m-%dT%H:%M:%SZ"), away, home])

    days = [(SEASON_START + timedelta(days=i - 1)).isoformat() for i in range(n_hist)]
    ranks = wl.ranks(pts)
    print("ranks Jan 12 -> Jan 13:", dict(zip(PEOPLE, zip(ranks[-2].tolist(), ranks[-1].tolist()))))
    games_by_index = defaultdict(list)
    for day, away, home in played:
        games_by_index[day + 1].append((away, home))

    data = {
        "meta": {
            "sample": True, "seed": seed, "season": LG.draft["season"], "now": NOW,
            "linesSource": f"{LG.lines_doc['source']}, {LG.lines_doc['asOf']}",
            "model": {"priorGames": wl.PRIOR_GAMES, "homeEdge": wl.HOME_EDGE, "sims": SIMS_TONIGHT},
        },
        "people": LG.people_json(),
        "teams": LG.teams_json(),
        "days": days,
        "games": [[day + 1, away, home, w] for (day, away, home), w in zip(played, winners)],
        "tonight": [{k: v for k, v in g.items() if k not in ("left",)} for g in TONIGHT],
        "demoOrder": DEMO_ORDER,
        "ahead": ahead,
        "series": {
            "points": pts.astype(int).tolist(),
            "vegas": np.round(vegas, 2).tolist(),
            "odds": np.round(odds, 4).tolist(),
            "rank": ranks.tolist(),
        },
        "oddsNow": [round(float(x), 4) for x in odds_now],
        "projNow": [round(float(x), 1) for x in proj_now],
        "oddsDemo": odds_demo,
        "bots": wl.vegas_bots(LG),
        "moments": wl.moments(LG, pts, games_by_index),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("window.SAMPLE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")

    print(f"seed {seed}; wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    print("lead changes:", [(days[i], PEOPLE[s]) for i, s in wl.lead_changes(pts)])
    print("moments:", [(days[i], t) for i, t in data["moments"]])
    print("odds now:", dict(zip(PEOPLE, data["oddsNow"])), "proj:", dict(zip(PEOPLE, data["projNow"])))
    print("preseason odds:", dict(zip(PEOPLE, data["series"]["odds"][0])))
    print("leverage:", [(g["away"] + "@" + g["home"], g["leverage"], g["winProb"]) for g in TONIGHT])
    print("odds after demo:", dict(zip(PEOPLE, odds_demo[-1])))
    print("longest streak:", longest_streaks(played, winners))


if __name__ == "__main__":
    main()
