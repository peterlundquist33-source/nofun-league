# NoFunLeague

Static site for the NoFunLeague — an eight-team Sleeper fantasy football league.

**Live:** https://peterlundquist33-source.github.io/nofun-league/

Standings, power rankings, a burn board, stats and analytics, the matchup
schedule and every draft the league has ever run.

## No API keys, no model calls

Everything on the site comes from [Sleeper's free public read
API](https://docs.sleeper.com/) (`api.sleeper.app/v1`), which needs no
authentication. There is deliberately **no LLM call anywhere** in this repo:

- the power rankings are a deterministic model (`tools/analyze.py`)
- the burns are format strings filled with real stats, picked by a hash of the
  week so the copy rotates but is reproducible
- the analytics are arithmetic over completed weeks

The same snapshot always renders the same page, and the whole thing costs
nothing to run.

## How it works

```
tools/snapshot.py   Sleeper  ->  data/*.json   (league, standings, schedule,
                                                scores, rosters, players,
                                                drafts, history, transactions)
tools/analyze.py    data/*.json -> data/analytics.json, power.json, burns.json
*.html + js/        read data/*.json in the browser and render
```

`.github/workflows/snapshot.yml` runs both scripts on a schedule (Tuesday and
Friday mornings in-season, Mondays year-round) and commits whatever changed.
It can also be run on demand from the Actions tab.

### Locally

```sh
python3 tools/snapshot.py      # ~15s, hits Sleeper
python3 tools/analyze.py
python3 -m http.server 8000    # then open http://localhost:8000
```

Both scripts are stdlib-only — no `pip install`.

## Burn board rules

The only subject is fantasy football: records, scoring, lineup decisions and
draft picks. Nothing about anybody's actual life goes into a template, ever.
New templates live in `BURNS` in `tools/analyze.py`.

## Team names

Names come straight from Sleeper (team name if set, otherwise the handle). To
show something else, add `tools/owners.json`:

```json
{ "998002547333902336": { "name": "Pete", "team": "Big Stickin" } }
```

Keys are Sleeper `user_id`s — see `data/teams.json` after a snapshot.
