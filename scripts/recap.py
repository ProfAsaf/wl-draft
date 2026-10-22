"""A dramatic recap of the most recent finished day, written from that day's results.

Plain templates, with the wording picked deterministically from the date so a given day
always reads the same and the next day sounds different.
"""
from __future__ import annotations

import random
from datetime import date

import wl

UPSET = 0.35  # a winner the line gave less than this chance


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def and_list(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def build(lg, day_iso, finals, gains, rank_before, rank_after, odds_before, odds_after, took_lead, por_record):
    """finals: that day's games (dicts with away, home, score and maybe spread).
    gains, rank_before/after and odds_before/after are per person; took_lead is the person
    who became sole leader that day (or None, or with back=True if they'd led before);
    por_record is Portland's (wins, losses) after the day."""
    rng = random.Random(day_iso)
    names = lg.people
    nick = lambda t: lg.info[t]["name"]  # noqa: E731
    d = date.fromisoformat(day_iso)
    stakes = [0] * lg.n
    games, upsets, used = [], [], set()
    for g in finals:
        a, h = g["away"], g["home"]
        home_won = g["score"][1] > g["score"][0]
        win, lose = (h, a) if home_won else (a, h)
        got = [s for s in range(lg.n) if s in (lg.w_owner[win], lg.l_owner[lose])]
        missed = [s for s in range(lg.n) if s in (lg.w_owner[lose], lg.l_owner[win])]
        for t in (a, h):
            for s in {lg.w_owner[t], lg.l_owner[t]} - {-1}:
                stakes[s] += 1
        hi, lo = max(g["score"]), min(g["score"])
        info = dict(win=win, lose=lose, hi=hi, lo=lo, got=got, missed=missed, margin=hi - lo)
        games.append(info)
        if "spread" in g and (got or missed):
            p_home = wl.spread_prob(g["spread"])
            p_win = p_home if home_won else 1 - p_home
            if p_win < UPSET:
                upsets.append((p_win, abs(g["spread"]), info))
    upsets.sort(key=lambda u: u[0])

    order = sorted(range(lg.n), key=lambda s: (-gains[s], names[s]))
    top = order[0]
    zero = [s for s in range(lg.n) if gains[s] == 0 and stakes[s] >= 3]

    # Headline: the biggest story of the day.
    if took_lead is not None:
        s, back = took_lead
        n = names[s]
        headline = rng.choice([f"{n} reclaims the throne", f"{n} is back on top", f"The crown returns to {n}"] if back
                              else [f"{n} seizes first place", f"A new No. 1: {n}", f"{n} storms to the top"])
    elif gains[top] >= 4 and gains[order[1]] < gains[top]:
        n, g = names[top], int(gains[top])
        headline = rng.choice([f"{n} erupts for +{g}", f"+{g}! {n} goes off", f"{n} had a night: +{g}"])
    elif zero:
        s = max(zero, key=lambda z: stakes[z])
        headline = rng.choice([f"{names[s]} goes 0-for-{stakes[s]}. Thoughts and prayers.",
                               f"A cold, dark night for {names[s]}: 0-for-{stakes[s]}"])
    elif upsets:
        _, _, u = upsets[0]
        used.add(id(u))
        headline = rng.choice([f"Stunner: the {nick(u['win'])} topple the {nick(u['lose'])}",
                               f"Chaos: the {nick(u['win'])} shock the {nick(u['lose'])}"])
    elif gains[top] > 0:
        headline = rng.choice([f"{names[top]} wins the night", f"{names[top]} takes the day, +{int(gains[top])}"])
    else:
        headline = "A quiet night. Too quiet."

    lines = ["The damage: " + ", ".join(f"{names[s]} {'+' if gains[s] else ''}{int(gains[s])}" for s in order) + "."]

    duels = sorted((g for g in games if g["got"] and g["missed"] and not set(g["got"]) & set(g["missed"])),
                   key=lambda g: g["margin"])
    for g in duels[:2]:
        used.add(id(g))
        w, lose = and_list(names[s] for s in g["got"]), and_list(names[s] for s in g["missed"])
        lines.append(rng.choice([
            f"{w} beat {lose} head-to-head as the {nick(g['win'])} took down the {nick(g['lose'])}, {g['hi']}-{g['lo']}.",
            f"In the {nick(g['win'])}-{nick(g['lose'])} duel, {w} got the better of {lose}, {g['hi']}-{g['lo']}.",
        ]))
    close = [g for g in games if g["margin"] <= 3 and g["got"] and id(g) not in used]
    if close:
        g = close[0]
        used.add(id(g))
        lines.append(f"Nail-biter: the {nick(g['win'])} edged the {nick(g['lose'])} {g['hi']}-{g['lo']}, "
                     f"good for {and_list(names[s] for s in g['got'])}.")
    for _, spread, u in upsets[:1]:
        if id(u) in used:
            continue
        thanks = f" {and_list(names[s] for s in u['got'])} say thanks." if u["got"] else ""
        lines.append(f"Upset alert: the {nick(u['win'])} won as {spread:g}-point underdogs.{thanks}")

    ups = [s for s in range(lg.n) if rank_after[s] < rank_before[s]]
    downs = [s for s in range(lg.n) if rank_after[s] > rank_before[s]]
    moves = [f"{names[s]} climbs to {ordinal(int(rank_after[s]))}" for s in ups]
    moves += [f"{names[s]} slides to {ordinal(int(rank_after[s]))}" for s in downs]
    if moves and took_lead is None:
        lines.append("; ".join(moves[:3]) + ".")

    if odds_before is not None:
        delta = [odds_after[s] - odds_before[s] for s in range(lg.n)]
        s = max(range(lg.n), key=lambda i: abs(delta[i]))
        if abs(delta[s]) >= 0.03:
            verb = rng.choice(["jump", "surge", "climb"]) if delta[s] > 0 else rng.choice(["tumble", "slip", "sink"])
            lines.append(f"{names[s]}'s title odds {verb} from {round(odds_before[s] * 100)}% to {round(odds_after[s] * 100)}%.")

    por = next((g for g in games if "POR" in (g["win"], g["lose"])), None)
    if por and lg.w_owner["POR"] >= 0 and lg.l_owner["POR"] >= 0:
        taker = names[lg.w_owner["POR"]] if por["win"] == "POR" else names[lg.l_owner["POR"]]
        lines.append(f"Portland Civil War: {taker} takes this round. It's {por_record[0]}-{por_record[1]} on the year.")

    lines.append(rng.choice(["The robots have seen enough.", "Adam Silver has been notified.", "Tonight, we go again.",
                             "Hydrate. Stretch. Check the Tonight tab.", "As always, Vegas is watching."]))
    return {"day": day_iso, "label": f"{d:%a}, {d:%b} {d.day}", "headline": headline, "lines": lines}
