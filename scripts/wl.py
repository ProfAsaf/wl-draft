"""League data and the title-odds model, shared by the live pipeline and the sample generator.

A pick is a team plus W or L: a W pick scores the team's wins, an L pick its losses.

Title odds come from simulating the rest of the season. Each team's preseason strength is
calibrated so that, over its real schedule, the model reproduces its Vegas line. That
strength is then blended with the team's record, with the line counting as PRIOR_GAMES
games. Every simulated season first draws how good each team really is from that
uncertainty and then plays out the remaining games.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SEASON_GAMES = 82
PRIOR_GAMES = 25  # weight of the preseason line, in games, when estimating strength
HOME_EDGE = 0.24  # log-odds bump for the home team (about 56% between equal teams)
MARGIN_SD = 12.0  # spread of an NBA game's final margin, in points
AVG = None        # opponent in a game not on the schedule yet: average strength, neutral court


def logit(p):
    return math.log(p / (1 - p))


def home_prob(p_home, p_away):
    """Home win probability between teams whose strengths are win rates against an average team."""
    return 1 / (1 + math.exp(-(logit(p_home) - logit(p_away) + HOME_EDGE)))


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def spread_prob(home_spread, lead=0, minutes_left=48.0):
    """Home win probability from the betting spread (negative means the home team is favored),
    updated for the score and the time left once the game is under way."""
    frac = max(minutes_left, 0.25) / 48
    return phi((lead - home_spread * frac) / (MARGIN_SD * math.sqrt(frac)))


class League:
    """The draft, the preseason lines and the teams, loaded from data/."""

    def __init__(self, data_dir: Path = DATA):
        self.draft = json.loads((data_dir / "draft.json").read_text(encoding="utf-8"))
        self.lines_doc = json.loads((data_dir / "preseason_lines.json").read_text(encoding="utf-8"))
        self.info = json.loads((data_dir / "teams.json").read_text(encoding="utf-8"))
        self.juice = self.lines_doc["lines"]
        self.lines = {t: v["total"] for t, v in self.juice.items()}
        self.teams = sorted(self.lines)
        self.tidx = {t: i for i, t in enumerate(self.teams)}
        self.people = self.draft["slots"]
        self.n = len(self.people)
        self.espn_season = int(self.draft["season"][:4]) + 1  # ESPN names a season by the year it ends
        self.p0 = {t: self.lines[t] / SEASON_GAMES for t in self.teams}
        self.picks = [[] for _ in self.people]  # (team, side, round, overall pick), in round order
        for r, row in enumerate(self.draft["rounds"]):
            order = range(self.n) if r % 2 == 0 else range(self.n - 1, -1, -1)
            for k, s in enumerate(order):
                team, side = row[s]
                self.picks[s].append((team, side, r + 1, r * self.n + k + 1))
        self.w_owner = {t: -1 for t in self.teams}
        self.l_owner = {t: -1 for t in self.teams}
        for s, picks in enumerate(self.picks):
            for team, side, _, _ in picks:
                (self.w_owner if side == "W" else self.l_owner)[team] = s
        self.by_espn = {self.info[t]["espnAbbr"]: t for t in self.teams}

    def person_points(self, wins, gp):
        """Points, and points minus the Vegas pace, per day (rows) and person (columns)."""
        pts = np.zeros((wins.shape[0], self.n))
        exp = np.zeros((wins.shape[0], self.n))
        for s, picks in enumerate(self.picks):
            for team, side, _, _ in picks:
                j = self.tidx[team]
                if side == "W":
                    pts[:, s] += wins[:, j]
                    exp[:, s] += self.p0[team] * gp[:, j]
                else:
                    pts[:, s] += gp[:, j] - wins[:, j]
                    exp[:, s] += (1 - self.p0[team]) * gp[:, j]
        return pts, pts - exp

    def points_matrices(self, games):
        """For (away, home) games: points each person gets if the home team wins (a) or loses (b)."""
        a = np.zeros((len(games), self.n), dtype=np.float32)
        b = np.zeros((len(games), self.n), dtype=np.float32)
        for g, (away, home) in enumerate(games):
            for winner, loser, m in ((home, away, a), (away, home, b)):
                if winner is not AVG and self.w_owner[winner] >= 0:
                    m[g, self.w_owner[winner]] += 1
                if loser is not AVG and self.l_owner[loser] >= 0:
                    m[g, self.l_owner[loser]] += 1
        return a, b

    def index_arrays(self, games):
        """Team indexes for (away, home) games, using len(teams) for an average opponent, and
        each game's home edge (none on the neutral court of a not-yet-scheduled game)."""
        nt = len(self.teams)
        home = np.array([self.tidx[h] for _, h in games], dtype=int)
        away = np.array([nt if a is AVG else self.tidx[a] for a, _ in games], dtype=int)
        edge = np.array([0.0 if a is AVG else HOME_EDGE for a, _ in games])
        return home, away, edge

    def people_json(self):
        return [
            {"name": name, "slot": s + 1,
             "picks": [{"team": t, "side": sd, "round": r, "overall": o} for t, sd, r, o in self.picks[s]]}
            for s, name in enumerate(self.people)
        ]

    def teams_json(self):
        return {
            t: {"city": self.info[t]["city"], "name": self.info[t]["name"], "color": self.info[t]["color"],
                "alt": self.info[t]["altColor"], "line": self.lines[t]}
            for t in self.teams
        }


def calibrate(league, games):
    """Win rates against an average team under which these (away, home) games reproduce the
    preseason lines. The posted lines add up to more wins than a season has, so they are
    scaled down to the real total first."""
    nt = len(league.teams)
    scale = nt * SEASON_GAMES / 2 / sum(league.lines.values())
    target = np.array([league.lines[t] * scale for t in league.teams])
    home, away, edge = league.index_arrays(games)
    real = away < nt
    theta = np.array([logit(league.p0[t]) for t in league.teams] + [0.0])
    for _ in range(300):
        p = 1 / (1 + np.exp(-(theta[home] - theta[away] + edge)))
        expected = np.bincount(home, p, nt) + np.bincount(away[real], 1 - p[real], nt)
        theta[:nt] += 0.5 * (np.log(target / expected) - np.log((SEASON_GAMES - target) / (SEASON_GAMES - expected)))
        theta[:nt] -= theta[:nt].mean()
    assert np.abs(expected - target).max() < 0.01, "calibration did not converge"
    return {t: 1 / (1 + math.exp(-theta[league.tidx[t]])) for t in league.teams}


def posterior(league, prior, wins_row, gp_row):
    """Beta parameters for each team's strength: the calibrated preseason line, worth
    PRIOR_GAMES games, plus the record so far."""
    p = np.array([prior[t] for t in league.teams])
    return PRIOR_GAMES * p + wins_row, PRIOR_GAMES * (1 - p) + (gp_row - wins_row)


def simulate(rng, current, alpha, beta, home_idx, away_idx, edge, a, b, sims, fixed=None):
    """Each simulated season's final points (sims x people) and its home-win draws.

    Every sim first draws how good each team really is from its posterior, Beta(alpha,
    beta), so the odds carry the uncertainty about team strength as well as game luck.
    `fixed` maps a game's column to a known home-win probability (tonight's games).
    """
    p_team = rng.beta(alpha, beta, size=(sims, len(alpha))).astype(np.float32)
    theta = np.log(p_team) - np.log1p(-p_team)
    theta = np.concatenate([theta, np.zeros((sims, 1), dtype=np.float32)], axis=1)  # average opponent
    p_home = 1 / (1 + np.exp(-(theta[:, home_idx] - theta[:, away_idx] + edge.astype(np.float32))))
    for k, prob in (fixed or {}).items():
        p_home[:, k] = prob
    h = (rng.random(p_home.shape, dtype=np.float32) < p_home).astype(np.float32)
    totals = current.astype(np.float32) + h @ a + (1 - h) @ b
    return totals, h.astype(bool)


def title_credit(totals):
    """Each sim's share of first place per person; ties split it."""
    win = totals == totals.max(axis=1, keepdims=True)
    return win / win.sum(axis=1, keepdims=True)


def ranks(pts):
    """Standings place per day and person: 1 + the number of people strictly ahead."""
    return (pts[:, None, :] > pts[:, :, None]).sum(axis=2) + 1


def lead_changes(pts):
    """(day index, person) whenever someone new holds the lead alone."""
    changes, cur = [], -1
    for i, row in enumerate(pts[1:], 1):
        top = np.flatnonzero(row == row.max())
        if len(top) == 1 and top[0] != cur:
            changes.append((i, int(top[0])))
            cur = int(top[0])
    return changes


def vegas_bots(league):
    """Each slot's bot takes the highest Vegas value left; ties go to the better juice."""
    def implied(o):
        return 100 / (o + 100) if o > 0 else -o / (-o + 100)

    options = []
    for t in league.teams:
        line = league.juice[t]
        p_over = implied(line["over"]) / (implied(line["over"]) + implied(line["under"]))
        fair = line["total"] + (p_over - 0.5) / 0.057  # juice-adjusted median wins
        options.append((line["total"], fair, t, "W"))
        options.append((SEASON_GAMES - line["total"], SEASON_GAMES - fair, t, "L"))
    options.sort(key=lambda o: (-o[0], -o[1], o[2]))
    bots = [[] for _ in league.people]
    for r in range(len(league.picks[0])):
        for s in (range(league.n) if r % 2 == 0 else range(league.n - 1, -1, -1)):
            _, _, team, side = options.pop(0)
            bots[s].append([team, side])
    return bots


def moments(league, pts, games_by_index):
    """Lead changes, 0-for-4-or-worse nights and the season's best night.

    games_by_index maps a day index (1 = the first day of games) to its (away, home) finals.
    """
    out, seen = [], set()
    for i, s in lead_changes(pts):
        out.append([i, f"{league.people[s]} {'back on top' if s in seen else 'takes the lead'}"])
        seen.add(s)
    if len(pts) < 2:
        return out
    daily = np.diff(pts, axis=0)
    for i in sorted(games_by_index):
        played = np.zeros(league.n, dtype=int)
        for away, home in games_by_index[i]:
            for t in (away, home):
                for s in {league.w_owner[t], league.l_owner[t]} - {-1}:
                    played[s] += 1
        for s in range(league.n):
            if played[s] >= 4 and daily[i - 1, s] == 0:
                out.append([i, f"{league.people[s]} goes 0-for-{played[s]}"])
    best = np.unravel_index(np.argmax(daily), daily.shape)
    if daily[best] > 0:
        out.append([int(best[0]) + 1, f"{league.people[best[1]]}'s best night: +{int(daily[best])}"])
    return sorted(out)
