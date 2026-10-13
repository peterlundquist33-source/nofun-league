#!/usr/bin/env python3
"""Snapshot the NoFunLeague Sleeper league into data/*.json.

Everything on this site comes from Sleeper's free public read API. There is no
LLM call anywhere in this repo: the power board, the analytics and even the
burns are computed from these snapshots by tools/analyze.py.

  python3 tools/snapshot.py

Writes: meta, league, teams, standings, schedule, scores, rosters, players,
drafts, history, transactions.
"""
import datetime
import json
import sys

from sleeper import LEAGUE_ID, TOOLS, get, pts, write

# Optional display-name overrides, keyed by Sleeper user_id:
#   {"998002547333902336": {"name": "Pete", "team": "Big Stickin"}}
# Sleeper handles are the default, so this file can stay empty.
OVERRIDES = json.loads((TOOLS / "owners.json").read_text()) \
    if (TOOLS / "owners.json").exists() else {}

LAST_WEEK = 18          # NFL regular season; covers every playoff week too
TXN_WEEKS = 18


# ------------------------------------------------------------------ identity

def team_identity(league_id):
    """roster_id -> {manager, team, handle, avatar} for one league season."""
    users = {u["user_id"]: u for u in (get(f"/league/{league_id}/users") or [])}
    rosters = get(f"/league/{league_id}/rosters") or []
    out = {}
    for r in rosters:
        rid = r["roster_id"]
        uid = r.get("owner_id")
        u = users.get(uid, {})
        meta = u.get("metadata") or {}
        ov = OVERRIDES.get(str(uid), {})
        handle = u.get("display_name") or f"Team {rid}"
        manager = ov.get("name") or handle
        team = ov.get("team") or (meta.get("team_name") or "").strip() or handle
        out[rid] = {
            "roster_id": rid,
            "manager": manager,
            "team": team,
            "handle": handle,
            "avatar": meta.get("avatar") or (
                f'https://sleepercdn.com/avatars/thumbs/{u["avatar"]}'
                if u.get("avatar") else None),
        }
    return out


def label(ident, rid):
    """The one name the site shows for a team. Stable across every page."""
    t = ident.get(rid)
    return t["team"] if t else f"Team {rid}"


# -------------------------------------------------------------------- chain

def league_chain():
    """[league dict, ...] newest season first, following previous_league_id."""
    chain, lid = [], LEAGUE_ID
    seen = set()
    while lid and lid not in seen:
        seen.add(lid)
        lg = get(f"/league/{lid}")
        if not lg:
            break
        chain.append(lg)
        lid = lg.get("previous_league_id")
    return chain


# ----------------------------------------------------------------- standings

def standings_for(league_id, ident):
    rows = []
    for r in get(f"/league/{league_id}/rosters") or []:
        s = r.get("settings") or {}
        rid = r["roster_id"]
        rows.append({
            "roster_id": rid,
            "team": label(ident, rid),
            "manager": ident.get(rid, {}).get("manager", f"Team {rid}"),
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "ties": s.get("ties", 0),
            "pf": pts(s),
            "pa": pts(s, "_against"),
            # ppts = max points possible from the roster, i.e. a perfect lineup
            "ppts": round((s.get("ppts") or 0) + (s.get("ppts_decimal") or 0) / 100, 2),
            "streak": (r.get("metadata") or {}).get("streak", ""),
            "form": (r.get("metadata") or {}).get("record", ""),
            "moves": s.get("total_moves", 0),
            "waiver_budget_used": s.get("waiver_budget_used", 0),
        })
    rows.sort(key=lambda x: (-x["wins"], -x["pf"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def bracket_results(league_id, ident):
    """(champion, runner_up, third) from the winners bracket, or (None, None, None)."""
    wb = get(f"/league/{league_id}/winners_bracket") or []
    if not wb:
        return None, None, None
    final = next((m for m in wb if m.get("p") == 1), None)
    third = next((m for m in wb if m.get("p") == 2), None) \
        or next((m for m in wb if m.get("p") == 3), None)
    champ = label(ident, final["w"]) if final and final.get("w") else None
    runner = label(ident, final["l"]) if final and final.get("l") else None
    bronze = label(ident, third["w"]) if third and third.get("w") else None
    return champ, runner, bronze


# ------------------------------------------------------------------ matchups

def weekly(league_id, ident, through, playoff_start):
    """(schedule, scores, player_week_points).

    schedule: [{week, games:[{a:{...}, b:{...}}, ...]}] including unplayed weeks.
    scores:   [{week, scores:{team: points}}] for scored weeks only.
    player:   {player_id: {"pts": total, "weeks": n, "owners": {team: pts}}}
    """
    schedule, scores, ppool = [], [], {}
    for wk in range(1, LAST_WEEK + 1):
        raw = get(f"/league/{league_id}/matchups/{wk}")
        if not raw:
            continue
        by_id, side = {}, {}
        for m in raw:
            rid = m["roster_id"]
            side[rid] = m
            by_id.setdefault(m.get("matchup_id"), []).append(rid)
        played = any((m.get("points") or 0) > 0 for m in raw)

        games = []
        for mid, rids in sorted((k, v) for k, v in by_id.items() if k is not None):
            if len(rids) != 2:
                continue
            pair = []
            for rid in sorted(rids):
                m = side[rid]
                pair.append({
                    "roster_id": rid,
                    "team": label(ident, rid),
                    "points": round(m.get("points") or 0, 2),
                })
            a, b = pair
            games.append({
                "matchup_id": mid,
                "a": a, "b": b,
                "played": played and (a["points"] > 0 or b["points"] > 0),
                "margin": round(abs(a["points"] - b["points"]), 2) if played else None,
                "winner": (a["team"] if a["points"] > b["points"]
                           else b["team"] if b["points"] > a["points"] else None)
                          if played else None,
            })
        if games:
            # Sleeper still returns matchup_ids for unplayed playoff weeks, but the
            # bracket isn't seeded yet, so those pairings are meaningless. Flag them
            # and let the page say "bracket TBD" instead of inventing a schedule.
            schedule.append({"week": wk, "played": played, "games": games,
                             "playoff": wk >= playoff_start})

        if not played or wk > through:
            continue
        wkscores = {}
        for m in raw:
            team = label(ident, m["roster_id"])
            wkscores[team] = round(m.get("points") or 0, 2)
            for pid, p in (m.get("players_points") or {}).items():
                if not p:
                    continue
                e = ppool.setdefault(str(pid), {"pts": 0.0, "weeks": 0, "owners": {}})
                e["pts"] = round(e["pts"] + p, 2)
                e["weeks"] += 1
                e["owners"][team] = round(e["owners"].get(team, 0) + p, 2)
            for pid in (m.get("starters") or []):
                if str(pid) in ppool:
                    ppool[str(pid)]["started"] = ppool[str(pid)].get("started", 0) + 1
        if wkscores:
            scores.append({"week": wk, "scores": wkscores})
    return schedule, scores, ppool


# ------------------------------------------------------------------- players

def player_universe(needed):
    """The full NFL player dict is ~10MB, so fetch once and keep only our ids."""
    print("  fetching player dictionary ...")
    allp = get("/players/nfl") or {}
    out = {}
    for pid in needed:
        p = allp.get(str(pid))
        if not p:
            # Defenses come back keyed by team abbreviation with no entry
            if str(pid).isalpha():
                out[str(pid)] = {"name": f"{pid} D/ST", "pos": "DEF",
                                 "team": str(pid), "age": None, "injury": None}
            continue
        nm = p.get("full_name") or " ".join(
            x for x in (p.get("first_name"), p.get("last_name")) if x)
        fpos = p.get("fantasy_positions") or (
            [p.get("position")] if p.get("position") else [])
        out[str(pid)] = {
            "name": nm or str(pid),
            "pos": (fpos[0] if fpos else ""),
            "team": p.get("team"),
            "age": p.get("age"),
            "injury": p.get("injury_status") or None,
        }
    return out


# -------------------------------------------------------------------- drafts

def drafts_for(league_id, season, ident):
    out = []
    for d in get(f"/league/{league_id}/drafts") or []:
        did = d["draft_id"]
        full = get(f"/draft/{did}") or {}
        picks = get(f"/draft/{did}/picks") or []
        out.append({
            "season": season,
            "draft_id": did,
            "type": full.get("type"),
            "status": full.get("status"),
            "rounds": (full.get("settings") or {}).get("rounds"),
            "picks": [{
                "round": p.get("round"),
                "pick": p.get("pick_no"),
                "slot": p.get("draft_slot"),
                "roster_id": p.get("roster_id"),
                "team": label(ident, p.get("roster_id")),
                "player_id": str(p.get("player_id")),
                "keeper": bool(p.get("is_keeper")),
            } for p in picks],
        })
    return out


# --------------------------------------------------------------- transactions

def transactions_for(league_id, ident):
    rows = []
    for wk in range(1, TXN_WEEKS + 1):
        for t in get(f"/league/{league_id}/transactions/{wk}") or []:
            if t.get("status") != "complete":
                continue
            rows.append({
                "week": t.get("leg", wk),
                "type": t.get("type"),
                "created": t.get("created"),
                "teams": sorted({label(ident, rid) for rid in t.get("roster_ids") or []}),
                "adds": {str(p): label(ident, rid) for p, rid in (t.get("adds") or {}).items()},
                "drops": {str(p): label(ident, rid) for p, rid in (t.get("drops") or {}).items()},
                "faab": (t.get("settings") or {}).get("waiver_bid"),
            })
    rows.sort(key=lambda r: r.get("created") or 0, reverse=True)
    return rows


# ----------------------------------------------------------------------- main

def main():
    chain = league_chain()
    if not chain:
        print("could not reach Sleeper")
        return 1
    cur = chain[0]
    season = int(cur["season"])
    settings = cur.get("settings") or {}
    print(f'league chain: {[c["season"] for c in chain]}  '
          f'(current {season}, {cur.get("status")})')

    state = get("/state/nfl") or {}
    ident = team_identity(LEAGUE_ID)

    playoff_start = settings.get("playoff_week_start") or 15
    # Sleeper's `leg` is the week in progress; the last week with final scores is
    # last_scored_leg. Rankings and analytics must only use completed weeks.
    scored = settings.get("last_scored_leg") or max(1, (settings.get("leg") or 1) - 1)
    # The week the site points at: the NFL's current week while the seasons line up,
    # otherwise the week after the last one that finished scoring.
    week = scored + 1
    if str(state.get("season")) == str(season) and state.get("week"):
        week = int(state["week"])
    week = max(1, min(week, LAST_WEEK))
    print(f"  current week {week} · last scored week {scored} "
          f"· regular season ends week {playoff_start - 1}")

    schedule, scores, ppool = weekly(LEAGUE_ID, ident, scored, playoff_start)

    rosters_raw = get(f"/league/{LEAGUE_ID}/rosters") or []
    needed = set(ppool)
    for r in rosters_raw:
        needed.update(str(p) for p in (r.get("players") or []))
    drafts = []
    history = []
    for lg in chain:
        lid, s = lg["league_id"], int(lg["season"])
        lg_ident = ident if lid == LEAGUE_ID else team_identity(lid)
        for d in drafts_for(lid, s, lg_ident):
            needed.update(p["player_id"] for p in d["picks"])
            drafts.append(d)
        champ, runner, third = bracket_results(lid, lg_ident)
        history.append({
            "season": s,
            "league_id": lid,
            "status": lg.get("status"),
            "champion": champ,
            "runner_up": runner,
            "third": third,
            "standings": standings_for(lid, lg_ident),
        })

    players = player_universe(needed)

    rosters_out = []
    for r in sorted(rosters_raw, key=lambda r: r["roster_id"]):
        rid = r["roster_id"]
        starters = [str(p) for p in (r.get("starters") or [])]
        rosters_out.append({
            **ident.get(rid, {"roster_id": rid}),
            "starters": starters,
            "players": [
                {"id": str(p), **players.get(str(p), {"name": str(p), "pos": ""}),
                 "starter": str(p) in starters,
                 "season_pts": ppool.get(str(p), {}).get("pts", 0)}
                for p in (r.get("players") or [])
            ],
        })

    write("meta", {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                             .isoformat(timespec="seconds"),
        "season": season,
        "week": week,
        "last_scored_week": scored,
        "playoff_week_start": playoff_start,
        "status": cur.get("status"),
        "league_id": LEAGUE_ID,
        "seasons": [int(c["season"]) for c in chain],
        "source": "Sleeper public read API (api.sleeper.app/v1)",
    })
    write("league", {
        "name": cur.get("name"),
        "season": season,
        "status": cur.get("status"),
        "teams": cur.get("total_rosters"),
        "roster_positions": [p for p in (cur.get("roster_positions") or [])],
        "scoring_settings": cur.get("scoring_settings") or {},
        "playoff_teams": settings.get("playoff_teams"),
        "playoff_week_start": playoff_start,
        "trade_deadline": settings.get("trade_deadline"),
        "waiver_type": settings.get("waiver_type"),
        "keeper_count": settings.get("max_keepers"),
    })
    write("teams", {"teams": [ident[k] for k in sorted(ident)]})
    write("standings", {"season": season, "rows": standings_for(LEAGUE_ID, ident)})
    write("schedule", {"season": season, "playoff_week_start": playoff_start,
                       "weeks": schedule})
    write("scores", {"season": season, "weeks": scores})
    write("rosters", {"season": season, "rosters": rosters_out})
    write("players", players)
    write("player-season", {"season": season, "players": ppool})
    write("drafts", {"drafts": sorted(drafts, key=lambda d: -d["season"])})
    write("history", {"seasons": sorted(history, key=lambda h: -h["season"])})
    write("transactions", {"season": season,
                           "rows": transactions_for(LEAGUE_ID, ident)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
