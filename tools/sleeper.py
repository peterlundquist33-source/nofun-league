"""Sleeper read-only client. Stdlib only, no credentials, no paid APIs.

Sleeper's v1 read API is public and unauthenticated, so there is nothing to
configure and nothing to leak. Every fetch retries a few times and then returns
None rather than raising, so one flaky endpoint can't take down a whole run.
"""
import json
import pathlib
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOOLS = ROOT / "tools"

BASE = "https://api.sleeper.app/v1"
LEAGUE_ID = "1389328340959100928"          # NoFunLeague — public league, not a secret
UA = "nofun-league-bot (+https://github.com/peterlundquist33-source/nofun-league)"


def get(path, tries=4):
    """GET BASE+path as JSON, or None after `tries` attempts."""
    url = BASE + path
    for i in range(tries):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if i == tries - 1:
                print(f"  ! {path}: {e}")
                return None
            time.sleep(1.5 * (i + 1))


def read(name):
    """Read a committed data/<name>.json, or None."""
    f = DATA / f"{name}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError as e:
        print(f"  ! data/{name}.json unreadable: {e}")
        return None


def write(name, obj):
    DATA.mkdir(exist_ok=True)
    f = DATA / f"{name}.json"
    f.write_text(json.dumps(obj, indent=2) + "\n")
    print(f"  wrote data/{name}.json  ({f.stat().st_size // 1024} KB)")


def pts(settings, key=""):
    """Sleeper splits fantasy points into integer + 2-digit decimal fields."""
    return round((settings.get(f"fpts{key}") or 0)
                 + (settings.get(f"fpts{key}_decimal") or 0) / 100, 2)
