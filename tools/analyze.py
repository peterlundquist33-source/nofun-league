#!/usr/bin/env python3
"""Derive analytics, the power board and the burns from the committed snapshots.

Reads data/*.json (written by tools/snapshot.py) and writes:

  analytics.json   all-play, luck, efficiency, scoring spread, records, top players
  power.json       the deterministic power board + a templated note per team
  burns.json       the trash-talk board, picked from templates by real stats

Nothing here calls a model. Every line of copy is a format string filled with a
number that came out of Sleeper, so the same snapshot always produces the same
page and the site costs nothing to run.

  python3 tools/analyze.py
"""
import datetime
import hashlib
import statistics
import sys

from sleeper import read, write

# ---- power model weights -------------------------------------------------
# The results half is what you've done; the ceiling half is the roster you're
# holding. Results dominate once a few weeks are in the books.
W_RESULTS, W_CEILING = 0.82, 0.18
# inside the results half
W_ALLPLAY, W_WINPCT, W_PF, W_FORM = 0.40, 0.16, 0.27, 0.17
FORM_WEEKS = 3

# Absolute index scales: 50 is the league average, K index points per unit above
# it. Deliberately not z-scored — z-scoring a bunched field makes tiny gaps look
# decisive, which is how a power board stops being believable.
K_PF = 0.9          # per point per game of actual scoring
K_CEILING = 0.8     # per point per game of perfect-lineup scoring

CLOSE_GAME = 10.0   # margin under this is a coin flip


# ------------------------------------------------------------------ utilities

def index(vals, k):
    """{key: raw} -> {key: 0-100} on an absolute scale around the league mean."""
    if not vals:
        return {}
    mean = sum(vals.values()) / len(vals)
    return {x: max(0.0, min(100.0, 50.0 + k * (v - mean))) for x, v in vals.items()}


def pct(rec):
    w, l, t = rec
    n = w + l + t
    return (w + 0.5 * t) / n if n else 0.0


def ordinal(n):
    sfx = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{sfx}"


def pick(options, *seed):
    """Deterministic choice: same snapshot -> same copy, but it rotates by week."""
    h = hashlib.sha256("|".join(str(s) for s in seed).encode()).hexdigest()
    return options[int(h, 16) % len(options)]


def allplay(weeks, teams):
    """{team: [w, l, t]} — every team against every other team, every week."""
    rec = {t: [0, 0, 0] for t in teams}
    for wk in weeks:
        sc = wk["scores"]
        for t, s in sc.items():
            if t not in rec:
                continue
            for o, so in sc.items():
                if o == t:
                    continue
                rec[t][0 if s > so else 1 if s < so else 2] += 1
    return rec


# ----------------------------------------------------------------- analytics

def build_analytics(meta, standings, scores, schedule, players, pseason, drafts,
                    transactions):
    rows = standings["rows"]
    teams = [r["team"] for r in rows]
    by_team = {r["team"]: r for r in rows}
    weeks = scores["weeks"]
    through = weeks[-1]["week"] if weeks else 0

    ap = allplay(weeks, teams)
    ap_pct = {t: pct(ap[t]) for t in teams}
    form = {t: pct(x) for t, x in allplay(weeks[-FORM_WEEKS:], teams).items()}

    per_team_scores = {t: [w["scores"][t] for w in weeks if t in w["scores"]]
                       for t in teams}

    scoring = []
    for t in teams:
        s = per_team_scores[t] or [0.0]
        scoring.append({
            "team": t,
            "weeks": s,
            "avg": round(sum(s) / len(s), 2),
            "high": max(s),
            "low": min(s),
            "stdev": round(statistics.pstdev(s), 2) if len(s) > 1 else 0.0,
        })
    scoring.sort(key=lambda x: -x["avg"])

    efficiency = []
    for r in rows:
        left = round(r["ppts"] - r["pf"], 2)
        efficiency.append({
            "team": r["team"],
            "pf": r["pf"], "ppts": r["ppts"],
            "eff": round(100 * r["pf"] / r["ppts"], 1) if r["ppts"] else 0.0,
            "left": left,
            "left_pg": round(left / len(per_team_scores[r["team"]] or [1]), 2),
        })
    efficiency.sort(key=lambda x: -x["eff"])

    luck = []
    for r in rows:
        real = pct([r["wins"], r["losses"], r["ties"]])
        luck.append({
            "team": r["team"],
            "real_pct": round(real, 3),
            "allplay_pct": round(ap_pct[r["team"]], 3),
            "allplay": f'{ap[r["team"]][0]}-{ap[r["team"]][1]}'
                       + (f'-{ap[r["team"]][2]}' if ap[r["team"]][2] else ""),
            "luck": round(real - ap_pct[r["team"]], 3),
            "expected_wins": round(ap_pct[r["team"]] * len(per_team_scores[r["team"]]), 2),
        })
    luck.sort(key=lambda x: -x["luck"])

    # ---- every completed game, for margins / records / close-game splits
    games = []
    for wk in schedule["weeks"]:
        for g in wk["games"]:
            if not g["played"] or not g["winner"]:
                continue
            hi, lo = sorted((g["a"], g["b"]), key=lambda s: -s["points"])
            games.append({"week": wk["week"], "winner": hi["team"], "loser": lo["team"],
                          "win_pts": hi["points"], "lose_pts": lo["points"],
                          "margin": round(hi["points"] - lo["points"], 2)})
    blowouts = sorted(games, key=lambda g: -g["margin"])[:5]
    nailbiters = sorted(games, key=lambda g: g["margin"])[:5]

    close = {t: [0, 0, 0] for t in teams}
    for g in games:
        if g["margin"] <= CLOSE_GAME:
            if g["winner"] in close:
                close[g["winner"]][0] += 1
            if g["loser"] in close:
                close[g["loser"]][1] += 1

    week_scores = [(w["week"], t, p) for w in weeks for t, p in w["scores"].items()]
    high = max(week_scores, key=lambda x: x[2]) if week_scores else None
    low = min(week_scores, key=lambda x: x[2]) if week_scores else None
    high_loss = max(games, key=lambda g: g["lose_pts"]) if games else None
    low_win = min(games, key=lambda g: g["win_pts"]) if games else None

    weekly_board = []
    for w in weeks:
        sc = sorted(w["scores"].items(), key=lambda kv: -kv[1])
        weekly_board.append({
            "week": w["week"],
            "high": {"team": sc[0][0], "pts": sc[0][1]},
            "low": {"team": sc[-1][0], "pts": sc[-1][1]},
            "avg": round(sum(v for _, v in sc) / len(sc), 2),
        })

    # ---- players: season points, who owns them, and position splits
    pool = pseason["players"]
    top_players = []
    for pid, e in pool.items():
        p = players.get(pid) or {}
        owner = max(e["owners"].items(), key=lambda kv: kv[1])[0] if e["owners"] else None
        top_players.append({
            "id": pid, "name": p.get("name", pid), "pos": p.get("pos", ""),
            "nfl": p.get("team"), "pts": e["pts"], "owner": owner,
            "weeks": e["weeks"],
        })
    top_players.sort(key=lambda x: -x["pts"])

    POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
    pos_pts = {t: {p: 0.0 for p in POSITIONS} for t in teams}
    for pid, e in pool.items():
        p = (players.get(pid) or {}).get("pos") or ""
        if p not in POSITIONS:
            continue
        for t, v in e["owners"].items():
            if t in pos_pts:
                pos_pts[t][p] = round(pos_pts[t][p] + v, 2)
    position = [{"team": t, **pos_pts[t]} for t in teams]

    # ---- draft value: this season's picks against the points they produced
    cur = next((d for d in drafts["drafts"] if d["season"] == meta["season"]), None)
    draft_value = []
    if cur:
        for pk in cur["picks"]:
            e = pool.get(pk["player_id"])
            p = players.get(pk["player_id"]) or {}
            draft_value.append({
                "round": pk["round"], "pick": pk["pick"], "team": pk["team"],
                "name": p.get("name", pk["player_id"]), "pos": p.get("pos", ""),
                "pts": (e or {}).get("pts", 0.0),
            })

    adds = [r for r in transactions["rows"] if r["type"] in ("waiver", "free_agent")]
    drafted = {pk["player_id"] for pk in (cur["picks"] if cur else [])}
    pickups = []
    for r in adds:
        for pid, team in r["adds"].items():
            if pid in drafted:
                continue
            e = pool.get(pid)
            if not e:
                continue
            p = players.get(pid) or {}
            pickups.append({"week": r["week"], "team": team,
                            "name": p.get("name", pid), "pos": p.get("pos", ""),
                            "pts": e["pts"]})
    pickups.sort(key=lambda x: -x["pts"])

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                             .isoformat(timespec="seconds"),
        "season": meta["season"],
        "through_week": through,
        "allplay": sorted(
            [{"team": t, "record": f'{ap[t][0]}-{ap[t][1]}'
              + (f'-{ap[t][2]}' if ap[t][2] else ""),
              "pct": round(ap_pct[t], 3), "form_pct": round(form.get(t, 0), 3)}
             for t in teams], key=lambda x: -x["pct"]),
        "luck": luck,
        "scoring": scoring,
        "efficiency": efficiency,
        "close_games": sorted(
            [{"team": t, "wins": close[t][0], "losses": close[t][1]} for t in teams],
            key=lambda x: (-x["wins"], x["losses"])),
        "blowouts": blowouts,
        "nailbiters": nailbiters,
        "records": {
            "high_week": {"team": high[1], "week": high[0], "pts": high[2]} if high else None,
            "low_week": {"team": low[1], "week": low[0], "pts": low[2]} if low else None,
            "high_loss": high_loss,
            "low_win": low_win,
        },
        "weekly_board": weekly_board,
        "top_players": top_players[:40],
        "position": position,
        "draft_value": draft_value,
        "pickups": pickups[:15],
        "standings_rank": {r["team"]: r["rank"] for r in rows},
        "moves": sorted([{"team": r["team"], "moves": r["moves"]} for r in rows],
                        key=lambda x: -x["moves"]),
    }


# --------------------------------------------------------------- power board

NOTES_TOP = [
    "Best in the league on the field and on the board. Nothing to argue about.",
    "Leads the league where it counts: the scoreboard, every week.",
    "Top of the board, and the all-play record says it isn't a fluke.",
]
NOTES_GOOD = [
    "Real contender. Scores enough to beat anybody on the schedule.",
    "Quietly one of the best teams here — no drama, just points.",
    "Right in the mix. One good month from the top seed.",
]
NOTES_MID = [
    "Exactly as average as the record looks. Beats the bottom, loses to the top.",
    "A .500 team in every direction. Entertaining, not frightening.",
    "Could finish anywhere. Nobody is planning around this team.",
]
NOTES_BAD = [
    "The schedule has been kind. The scoring has not.",
    "Losing more games than the roster should. Something has to change.",
    "Below the line and sliding. The math is not sympathetic.",
]
NOTES_BOTTOM = [
    "Last on the board, last in all-play, last in excuses that work.",
    "The floor of the league. Playing for draft position already.",
    "Bottom of the board and not close to the team above it.",
]


def build_power(meta, standings, analytics, prev):
    rows = standings["rows"]
    teams = [r["team"] for r in rows]
    by_team = {r["team"]: r for r in rows}
    through = analytics["through_week"]
    gp = {s["team"]: len(s["weeks"]) for s in analytics["scoring"]}

    ap = {a["team"]: a["pct"] for a in analytics["allplay"]}
    fm = {a["team"]: a["form_pct"] for a in analytics["allplay"]}
    win = {r["team"]: pct([r["wins"], r["losses"], r["ties"]]) for r in rows}
    pf_pg = {t: round(by_team[t]["pf"] / max(1, gp.get(t, 1)), 2) for t in teams}
    ceil_pg = {t: round(by_team[t]["ppts"] / max(1, gp.get(t, 1)), 2) for t in teams}

    i_pf = index(pf_pg, K_PF)
    i_ceil = index(ceil_pg, K_CEILING)

    out = []
    for t in teams:
        results = (W_ALLPLAY * 100 * ap.get(t, 0)
                   + W_WINPCT * 100 * win[t]
                   + W_PF * i_pf[t]
                   + W_FORM * 100 * fm.get(t, 0))
        score = W_RESULTS * results + W_CEILING * i_ceil[t]
        out.append({
            "team": t,
            "manager": by_team[t]["manager"],
            "score": round(score, 1),
            "record": f'{by_team[t]["wins"]}-{by_team[t]["losses"]}'
                      + (f'-{by_team[t]["ties"]}' if by_team[t]["ties"] else ""),
            "allplay": next(a["record"] for a in analytics["allplay"] if a["team"] == t),
            "allplay_pct": round(ap.get(t, 0), 3),
            "pf_pg": pf_pg[t],
            "ceiling_pg": ceil_pg[t],
            "form_pct": round(fm.get(t, 0), 3),
            "standings_rank": by_team[t]["rank"],
        })

    # The displayed score IS the ordering key, so a lower score can never sit
    # above a higher one. Ties break on points per game, then team name.
    out.sort(key=lambda r: (-r["score"], -r["pf_pg"], r["team"]))
    n = len(out)
    for i, r in enumerate(out, 1):
        r["rank"] = i
        was = (prev or {}).get(r["team"])
        r["prev_rank"] = was
        r["move"] = (was - i) if was else 0
        band = (NOTES_TOP if i == 1 else
                NOTES_BOTTOM if i == n else
                NOTES_GOOD if i <= max(2, n // 3) else
                NOTES_BAD if i > n - max(2, n // 3) else
                NOTES_MID)
        r["note"] = pick(band, through, r["team"], i)

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                             .isoformat(timespec="seconds"),
        "season": meta["season"],
        "through_week": through,
        "model": {
            "results_weight": W_RESULTS, "ceiling_weight": W_CEILING,
            "allplay": W_ALLPLAY, "win_pct": W_WINPCT,
            "points_for": W_PF, "recent_form": W_FORM, "form_weeks": FORM_WEEKS,
        },
        "rows": out,
    }


# ---------------------------------------------------------------- burns board
#
# Rules for everything in this section: the only subject is fantasy football —
# a team's record, its scoring, its lineup decisions and its draft. Nothing
# about anybody's actual life goes in a template, ever.

BURNS = {
    "cellar": ("Basement Dweller", [
        "{team} is {record}. At some point that stops being bad luck and starts being a roster.",
        "{record}. {team} has turned every Sunday into a formality for the opponent.",
        "{team} sits {record} and is the only reason anyone else feels good about their season.",
    ]),
    "skid": ("Active Skid", [
        "{team} has lost {n} straight. The streak is now the most consistent thing about this team.",
        "{n} losses in a row for {team}. Each one somehow a little more avoidable than the last.",
        "{team}: {n}-game skid and counting. The lineup changes, the result doesn't.",
    ]),
    "bench": ("Points Left On The Bench", [
        "{team} has stranded {left} points on the bench — {left_pg} a week of pure lineup malpractice.",
        "{left} points watched from the bench in {team}'s honor. Setting a lineup is part of the game.",
        "{team} is only {eff}% efficient. The roster is fine; the person submitting it is the problem.",
    ]),
    "lucky": ("Luckiest Team Alive", [
        "{team} is {record} but only {allplay} against the whole league. The schedule is doing the heavy lifting.",
        "{team} should be {exp} wins by all-play. Instead: {record}. Enjoy it while the calendar allows.",
        "Nobody has been handed more than {team} — {record} on {allplay} play.",
    ]),
    "unlucky": ("Robbed Weekly", [
        "{team} plays to an {allplay} all-play record and has {record} to show for it. Brutal schedule.",
        "{team} would be {exp} wins against an average slate. The bracket won't care.",
        "{team}: good enough to beat most of the league most weeks, and {record} anyway.",
    ]),
    "floor": ("Lowest Score Of The Season", [
        "{team} put up {pts} in Week {week}. A bye week would have been competitive.",
        "{pts} points, Week {week}, {team}. That's not a bad week, that's a forfeit with extra steps.",
        "Week {week}: {team} managed {pts}. The league average that week was {avg}.",
    ]),
    "blowout": ("Worst Beating So Far", [
        "{winner} beat {loser} by {margin} in Week {week}. {lose_pts} to {win_pts} isn't a loss, it's a receipt.",
        "Week {week}: {loser} lost to {winner} by {margin}. Mercy rules exist for a reason.",
        "{winner} {win_pts}, {loser} {lose_pts}. A {margin}-point hug from Week {week}.",
    ]),
    "pa": ("Punching Bag", [
        "{team} has absorbed {pa} points against — the most in the league, by a wide margin.",
        "Everyone scores on {team}. {pa} points against and counting.",
        "{pa} points allowed. {team} is the league's favorite week on the schedule.",
    ]),
    "coinflip": ("Can't Win Close", [
        "{team} is {w}-{l} in games inside {close} points. Clutch is apparently optional.",
        "{l} losses by single digits for {team}. The margins are cruel and the lineup isn't helping.",
        "{team} keeps it close and loses anyway: {w}-{l} in coin-flip games.",
    ]),
    "bust": ("Draft Day Regret", [
        "{team} spent a round {round} pick on {name} and has {pts} points to show for it.",
        "Round {round}, overall pick {pick}: {name}. {team} is still waiting on delivery.",
        "{name} in round {round} was {team}'s big swing. {pts} points later, it's a cautionary tale.",
    ]),
    "gem": ("Actually A Good Pick", [
        "{team} got {name} in round {round} for {pts} points. One good decision, grudgingly acknowledged.",
        "Round {round}: {name}, {pts} points, {team}. Broken clocks and all that.",
        "{name} has {pts} points after going in round {round} to {team}. Credit where it's due, and nowhere else.",
    ]),
    "ceiling": ("Best Roster, Worst Manager", [
        "{team} has the {ceil_rank} best roster ceiling and sits {rank} in the standings. The talent isn't the issue.",
        "{team} could be scoring {ceiling} a week. It's scoring {pf_pg}. Draw your own conclusion.",
        "{ceiling} points available per week, {pf_pg} actually used. {team} is beating itself.",
    ]),
    "volatile": ("Pick A Lane", [
        "{team} swings {stdev} points week to week — high of {high}, low of {low}. Nobody knows what shows up.",
        "{high} one week, {low} another. {team} is a coin with a hole in it.",
        "{team}'s standard deviation is {stdev}. That's not a team, that's a weather pattern.",
    ]),
    "churn": ("Waiver Wire Addict", [
        "{team} has made {moves} roster moves. None of them fixed anything.",
        "{moves} transactions for {team}. Churn is not a strategy.",
        "{team} treats the waiver wire like a personality: {moves} moves and counting.",
    ]),
    "lowwin": ("Won With Nothing", [
        "{winner} won Week {week} with {win_pts} points. {loser} managed {lose_pts}. Somebody had to.",
        "Week {week} gave us {winner} {win_pts} over {loser} {lose_pts}. Football was the real loser.",
    ]),
    "highloss": ("Scored Big, Lost Anyway", [
        "{loser} put up {lose_pts} in Week {week} and lost. That one stings for the rest of the season.",
        "Week {week}: {lose_pts} points from {loser}, still a loss to {winner}. The schedule is undefeated.",
    ]),
}


def burn(tag, fields, through):
    title, templates = BURNS[tag]
    line = pick(templates, through, tag).format(**fields)
    return {"tag": tag, "title": title, "line": line}


def build_burns(meta, standings, analytics):
    rows = standings["rows"]
    by_team = {r["team"]: r for r in rows}
    through = analytics["through_week"]
    items = []

    def add(tag, **f):
        try:
            items.append(burn(tag, f, through))
        except (KeyError, IndexError, TypeError) as e:
            print(f"  ! burn {tag} skipped: {e}")

    last = rows[-1]
    add("cellar", team=last["team"],
        record=f'{last["wins"]}-{last["losses"]}'
               + (f'-{last["ties"]}' if last["ties"] else ""))

    skids = [(r["team"], int(r["streak"][:-1]))
             for r in rows if r["streak"].endswith("L") and r["streak"][:-1].isdigit()]
    if skids:
        t, n = max(skids, key=lambda x: x[1])
        if n >= 2:
            add("skid", team=t, n=n)

    worst_eff = min(analytics["efficiency"], key=lambda e: e["eff"])
    add("bench", team=worst_eff["team"], left=worst_eff["left"],
        left_pg=worst_eff["left_pg"], eff=worst_eff["eff"])

    lucky = analytics["luck"][0]
    if lucky["luck"] > 0.05:
        add("lucky", team=lucky["team"],
            record=f'{by_team[lucky["team"]]["wins"]}-{by_team[lucky["team"]]["losses"]}',
            allplay=lucky["allplay"], exp=lucky["expected_wins"])

    unlucky = analytics["luck"][-1]
    if unlucky["luck"] < -0.05:
        add("unlucky", team=unlucky["team"],
            record=f'{by_team[unlucky["team"]]["wins"]}-{by_team[unlucky["team"]]["losses"]}',
            allplay=unlucky["allplay"], exp=unlucky["expected_wins"])

    lw = analytics["records"]["low_week"]
    if lw:
        wk_avg = next((w["avg"] for w in analytics["weekly_board"]
                       if w["week"] == lw["week"]), "")
        add("floor", team=lw["team"], pts=lw["pts"], week=lw["week"], avg=wk_avg)

    if analytics["blowouts"]:
        add("blowout", **analytics["blowouts"][0])

    worst_pa = max(rows, key=lambda r: r["pa"])
    add("pa", team=worst_pa["team"], pa=worst_pa["pa"])

    cf = [c for c in analytics["close_games"] if c["losses"] >= 2]
    if cf:
        c = max(cf, key=lambda x: (x["losses"], -x["wins"]))
        add("coinflip", team=c["team"], w=c["wins"], l=c["losses"], close=int(CLOSE_GAME))

    early = [d for d in analytics["draft_value"] if d["round"] <= 3]
    if early:
        b = min(early, key=lambda d: d["pts"])
        add("bust", team=b["team"], pick=b["pick"], round=b["round"],
            name=b["name"], pts=b["pts"])
    late = [d for d in analytics["draft_value"] if d["round"] >= 7]
    if late:
        g = max(late, key=lambda d: d["pts"])
        if g["pts"] > 0:
            add("gem", team=g["team"], pick=g["pick"], round=g["round"],
                name=g["name"], pts=g["pts"])

    ceil = sorted(rows, key=lambda r: -r["ppts"])
    gp = {s["team"]: max(1, len(s["weeks"])) for s in analytics["scoring"]}
    for i, r in enumerate(ceil, 1):
        if r["rank"] - i >= 3:       # strong roster, weak standings slot
            add("ceiling", team=r["team"], ceil_rank=ordinal(i), rank=ordinal(r["rank"]),
                ceiling=round(r["ppts"] / gp[r["team"]], 1),
                pf_pg=round(r["pf"] / gp[r["team"]], 1))
            break

    vol = max(analytics["scoring"], key=lambda s: s["stdev"])
    if vol["stdev"] > 0:
        add("volatile", team=vol["team"], stdev=vol["stdev"],
            high=vol["high"], low=vol["low"])

    churn = analytics["moves"][0]
    if churn["moves"] >= 5:
        add("churn", team=churn["team"], moves=churn["moves"])

    lwin = analytics["records"]["low_win"]
    if lwin:
        add("lowwin", **lwin)
    hloss = analytics["records"]["high_loss"]
    if hloss:
        add("highloss", **hloss)

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                             .isoformat(timespec="seconds"),
        "season": meta["season"],
        "through_week": through,
        "disclaimer": "Every line is generated from this league's Sleeper stats. "
                      "Fantasy football only.",
        "items": items,
    }


# ----------------------------------------------------------------------- main

def main():
    need = ["meta", "standings", "scores", "schedule", "players", "player-season",
            "drafts", "transactions"]
    loaded = {n: read(n) for n in need}
    missing = [n for n, v in loaded.items() if not v]
    if missing:
        print(f"missing snapshots: {missing} — run tools/snapshot.py first")
        return 1
    if not loaded["scores"]["weeks"]:
        print("no scored weeks yet — analytics, power and burns need at least one")
        return 0

    analytics = build_analytics(
        loaded["meta"], loaded["standings"], loaded["scores"], loaded["schedule"],
        loaded["players"], loaded["player-season"], loaded["drafts"],
        loaded["transactions"])
    write("analytics", analytics)

    old = read("power") or {}
    prev = {r["team"]: r["rank"] for r in old.get("rows", [])} \
        if old.get("through_week") not in (None, analytics["through_week"]) \
        else {r["team"]: r.get("prev_rank") for r in old.get("rows", [])}
    power = build_power(loaded["meta"], loaded["standings"], analytics,
                        {k: v for k, v in prev.items() if v})
    write("power", power)
    print("  power board: " + ", ".join(f'{r["rank"]}. {r["team"]} {r["score"]}'
                                        for r in power["rows"]))

    burns = build_burns(loaded["meta"], loaded["standings"], analytics)
    write("burns", burns)
    print(f'  burns: {len(burns["items"])} items')
    return 0


if __name__ == "__main__":
    sys.exit(main())
