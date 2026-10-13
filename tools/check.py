#!/usr/bin/env python3
"""Assert the snapshots are internally consistent before they get published.

Runs in CI between the snapshot and the commit, so a half-fetched or
self-contradicting data set never reaches the live site.

  python3 tools/check.py
"""
import sys

from sleeper import read

FILES = ["meta", "league", "teams", "standings", "schedule", "scores", "rosters",
         "players", "player-season", "drafts", "history", "transactions",
         "analytics", "power", "burns"]

fails = []


def ok(cond, msg):
    if not cond:
        fails.append(msg)


def main():
    d = {}
    for n in FILES:
        d[n] = read(n)
        ok(d[n] is not None, f"data/{n}.json is missing or unreadable")
    if fails:
        for f in fails:
            print("FAIL", f)
        return 1

    meta, league = d["meta"], d["league"]
    rows = d["standings"]["rows"]
    teams = {r["team"] for r in rows}

    ok(len(rows) == league["teams"],
       f'standings has {len(rows)} rows, league says {league["teams"]} teams')
    ok(len(teams) == len(rows), "two teams share a display name")
    ok(league["name"] == "NoFunLeague", f'league name is {league["name"]!r}')
    ok(meta["last_scored_week"] <= meta["week"],
       "last scored week is ahead of the current week")

    # Wins and losses must balance across the league (ties counted twice).
    w = sum(r["wins"] for r in rows)
    l = sum(r["losses"] for r in rows)
    ok(w == l, f"league record doesn't balance: {w} wins vs {l} losses")

    for r in rows:
        ok(r["ppts"] >= r["pf"] - 0.01,
           f'{r["team"]}: perfect-lineup points ({r["ppts"]}) below actual ({r["pf"]})')
        ok(r["pf"] > 0, f'{r["team"]} has no points for')

    # Standings order: wins, then points for.
    keys = [(-r["wins"], -r["pf"]) for r in rows]
    ok(keys == sorted(keys), "standings are not sorted by wins then points for")

    # Every scored week covers every team exactly once.
    for wk in d["scores"]["weeks"]:
        ok(set(wk["scores"]) == teams,
           f'week {wk["week"]} scores cover {len(wk["scores"])} of {len(teams)} teams')

    # Schedule: a played week's scores must match the scores file.
    sc = {w["week"]: w["scores"] for w in d["scores"]["weeks"]}
    for wk in d["schedule"]["weeks"]:
        if wk["week"] not in sc:
            continue
        for g in wk["games"]:
            for side in (g["a"], g["b"]):
                want = sc[wk["week"]].get(side["team"])
                ok(want is not None and abs(want - side["points"]) < 0.01,
                   f'week {wk["week"]}: {side["team"]} scores '
                   f'{side["points"]} in schedule, {want} in scores')

    # Power board: the displayed score is the ordering key, so it must never
    # increase as the rank number grows.
    pr = d["power"]["rows"]
    ok(len(pr) == len(rows), "power board is missing teams")
    ok([r["rank"] for r in pr] == list(range(1, len(pr) + 1)),
       "power ranks are not 1..N in order")
    for a, b in zip(pr, pr[1:]):
        ok(a["score"] >= b["score"],
           f'power board out of order: #{a["rank"]} {a["team"]} {a["score"]} '
           f'is below #{b["rank"]} {b["team"]} {b["score"]}')
    for r in pr:
        ok(r["team"] in teams, f'power board has unknown team {r["team"]!r}')

    # Analytics: all-play games played must be identical for every team.
    ap = d["analytics"]["allplay"]
    counts = {sum(int(x) for x in a["record"].split("-")) for a in ap}
    ok(len(counts) == 1, f"all-play game counts differ between teams: {counts}")
    ok(len(ap) == len(rows), "all-play table is missing teams")

    # Burns: present, formatted, and free of unfilled placeholders.
    items = d["burns"]["items"]
    ok(len(items) >= 5, f"only {len(items)} burns generated")
    for b in items:
        ok("{" not in b["line"] and "}" not in b["line"],
           f'burn {b["tag"]} has an unfilled placeholder: {b["line"]}')
        ok(b["line"].strip().endswith("."), f'burn {b["tag"]} has no closing period')
        ok(len(b["line"]) > 25, f'burn {b["tag"]} is suspiciously short')

    # No stray nulls where a page expects text.
    for r in d["teams"]["teams"]:
        ok(r["team"] and r["manager"], f'roster {r["roster_id"]} has no name')

    for f in fails:
        print("FAIL", f)
    if fails:
        print(f"\n{len(fails)} check(s) failed")
        return 1
    print(f'checks passed · {len(rows)} teams · week {meta["week"]} '
          f'· {len(d["scores"]["weeks"])} scored weeks '
          f'· {len(items)} burns · {len(d["history"]["seasons"])} seasons')
    return 0


if __name__ == "__main__":
    sys.exit(main())
