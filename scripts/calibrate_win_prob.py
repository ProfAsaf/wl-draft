"""Fit the live win-probability model's one number, the spread of scoring over a game, to real games.

The page's live chance to win uses only the score, the time left and who has the ball: the
current margin plus normal noise whose standard deviation is SIGMA points over 48 minutes,
shrinking with the square root of the time left (Stern's 1994 random-walk model of NBA scores).
This script picks SIGMA as the value that best predicted the winners of a full season's games
from each quarter break (end of the 1st, halftime, end of the 3rd), then shows how well that
calibration holds, lead by lead.

    python scripts/calibrate_win_prob.py            # uses data/quarter_scores_2025_26.json
    python scripts/calibrate_win_prob.py --download # refetches that file from ESPN first
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

import espn

DATA = Path(__file__).resolve().parent.parent / "data" / "quarter_scores_2025_26.json"
SEASON = (date(2025, 10, 21), date(2026, 4, 13))  # the 2025-26 regular season
BREAKS = ((1, 36, "end of Q1"), (2, 24, "halftime"), (3, 12, "end of Q3"))  # quarters played, minutes left


def download():
    """[away quarters, home quarters] for every finished regular-season game, overtimes included."""
    games = []
    day = SEASON[0]
    while day <= SEASON[1]:
        for e in espn.scoreboard(day).get("events", []):
            comp = e["competitions"][0]
            if (e.get("season") or {}).get("type") != espn.REGULAR_SEASON or not comp["status"]["type"].get("completed"):
                continue
            side = {k["homeAway"]: [int(float(x.get("value", 0))) for x in k.get("linescores", [])] for k in comp["competitors"]}
            if len(side.get("away", [])) >= 4 and len(side["away"]) == len(side.get("home", [])):
                games.append([side["away"], side["home"]])
        day += timedelta(days=1)
    DATA.write_text(json.dumps(games, separators=(",", ":")) + "\n", encoding="utf-8")
    return games


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def main():
    games = download() if "--download" in sys.argv or not DATA.exists() else json.loads(DATA.read_text(encoding="utf-8"))
    margin = np.cumsum([[h - a for a, h in zip(away[:4], home[:4])] for away, home in games], axis=1)  # home lead after each quarter
    won = np.array([sum(home) > sum(away) for away, home in games])
    print(f"{len(games)} games")

    def log_loss(sigma, lead, left):
        p = np.clip([phi(x / (sigma * math.sqrt(left / 48))) for x in lead], 1e-6, 1 - 1e-6)
        return -np.mean(won * np.log(p) + ~won * np.log(1 - p))

    grid = np.arange(12, 26.01, 0.5)
    total = sum(np.array([log_loss(s, margin[:, q - 1], left) for s in grid]) for q, left, _ in BREAKS)
    sigma = float(grid[total.argmin()])
    print(f"best sigma: {sigma} points per 48 minutes")
    for q, left, name in BREAKS[1:]:
        lead = margin[:, q - 1]
        print(f"{name}: the leader's chance, predicted / actual (games)")
        for lo, hi in ((1, 4), (4, 7), (7, 10), (10, 13), (13, 17), (17, 21), (21, 99)):
            pick = (np.abs(lead) >= lo) & (np.abs(lead) < hi)
            if pick.any():
                actual = np.where(lead[pick] > 0, won[pick], ~won[pick]).mean()
                predicted = np.mean([phi(abs(x) / (sigma * math.sqrt(left / 48))) for x in lead[pick]])
                print(f"  up {lo:2d}-{hi - 1:2d}: {predicted:.0%} / {actual:.0%} ({pick.sum()})")


if __name__ == "__main__":
    main()
