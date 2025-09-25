#!/usr/bin/env python3
"""
hawks_dump_games_console.py

Pretty console dump of Chicago Blackhawks game data from data_fetch.py:
- LAST game       (date label + final score)
- LIVE game       (status + current score if available)
- NEXT game       (opponent + time with Today/Tonight/Tomorrow/Yesterday)
- NEXT HOME game  (optional convenience block)

Usage:
  python3 hawks_dump_games_console.py
  python3 hawks_dump_games_console.py --no-next-home  # hide next-home block
"""

from __future__ import annotations
import argparse
import datetime
from typing import Any, Dict, Optional, Tuple

import data_fetch
import config

# Abbreviation map for nicer console output
NHL_ABBR = {
    "Anaheim Ducks": "ANA",
    "Boston Bruins": "BOS",
    "Buffalo Sabres": "BUF",
    "Carolina Hurricanes": "CAR",
    "Columbus Blue Jackets": "CBJ",
    "Calgary Flames": "CGY",
    "Chicago Blackhawks": "CHI",
    "Colorado Avalanche": "COL",
    "Dallas Stars": "DAL",
    "Detroit Red Wings": "DET",
    "Edmonton Oilers": "EDM",
    "Florida Panthers": "FLA",
    "Los Angeles Kings": "LAK",
    "Minnesota Wild": "MIN",
    "Montréal Canadiens": "MTL",
    "New Jersey Devils": "NJD",
    "Nashville Predators": "NSH",
    "New York Islanders": "NYI",
    "New York Rangers": "NYR",
    "Ottawa Senators": "OTT",
    "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT",
    "Seattle Kraken": "SEA",
    "San Jose Sharks": "SJS",
    "St. Louis Blues": "STL",
    "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR",
    "Utah Hockey Club": "UTA",
    "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK",
    "Winnipeg Jets": "WPG",
    "Washington Capitals": "WSH",
}

# Some feeds use short/nickname forms — map them to full names
NICK_TO_FULL = {
    "Blackhawks": "Chicago Blackhawks",
    "Red Wings": "Detroit Red Wings",
    "Kings": "Los Angeles Kings",
    "Canadiens": "Montréal Canadiens",
    "Leafs": "Toronto Maple Leafs",
    "Penguins": "Pittsburgh Penguins",
    "Rangers": "New York Rangers",
    "Islanders": "New York Islanders",
    "Devils": "New Jersey Devils",
    "Lightning": "Tampa Bay Lightning",
    "Panthers": "Florida Panthers",
    "Sabres": "Buffalo Sabres",
    "Bruins": "Boston Bruins",
    "Senators": "Ottawa Senators",
    "Flyers": "Philadelphia Flyers",
    "Capitals": "Washington Capitals",
    "Jackets": "Columbus Blue Jackets",
    "Hurricanes": "Carolina Hurricanes",
    "Predators": "Nashville Predators",
    "Blues": "St. Louis Blues",
    "Wings": "Detroit Red Wings",
    "Jets": "Winnipeg Jets",
    "Ducks": "Anaheim Ducks",
    "Sharks": "San Jose Sharks",
    "Kraken": "Seattle Kraken",
    "Canucks": "Vancouver Canucks",
    "Flames": "Calgary Flames",
    "Oilers": "Edmonton Oilers",
    "Stars": "Dallas Stars",
    "Avalanche": "Colorado Avalanche",
    "Golden Knights": "Vegas Golden Knights",
    "Wild": "Minnesota Wild",
    "Coyotes": "Utah Hockey Club",  # legacy → Utah
    "Utah": "Utah Hockey Club",
    "Mammoth": "Utah Hockey Club",
}

# ────────────────────────────────────────────────────────────────────────────
# Helpers

def _safe(d: Dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default

def _team_name(team_obj: Any) -> str:
    """
    Pull a readable team name from a variety of possible fields in NHL feeds.
    """
    if not isinstance(team_obj, dict):
        return "UNK"

    cn = team_obj.get("commonName")
    if isinstance(cn, dict) and cn.get("default"):
        return cn["default"]

    for k in ("commonName", "name", "teamName", "shortName"):
        v = team_obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    ab = team_obj.get("abbrev")
    if isinstance(ab, str) and ab.strip():
        # if all we have is an abbrev, return that
        return ab.strip().upper()

    return "UNK"

def _full_name(name: str) -> str:
    if name in NHL_ABBR:
        return name
    if name in NICK_TO_FULL:
        return NICK_TO_FULL[name]
    # Heuristic suffixes
    if name.endswith("Red Wings"): return "Detroit Red Wings"
    if name.endswith("Blackhawks"): return "Chicago Blackhawks"
    return name

def _abbr(full_name: str) -> str:
    return NHL_ABBR.get(full_name, full_name[:3].upper() if full_name and full_name != "UNK" else "UNK")

def _extract_teams(game: Dict[str, Any]) -> Optional[Tuple[Dict, Dict]]:
    away = _safe(game, "awayTeam", default=None) or _safe(game, "away_team", default=None) or _safe(game, "teams", "away", default=None)
    home = _safe(game, "homeTeam", default=None) or _safe(game, "home_team", default=None) or _safe(game, "teams", "home", default=None)
    if not isinstance(away, dict) or not isinstance(home, dict):
        return None
    return away, home

def _rel_label_for_next_or_live(official_date: str, start_time_central: str) -> str:
    """
    For next/live: Today/Tonight/Tomorrow/Yesterday + time (if known),
    else 'Tue 9/9' (time appended if present).
    """
    today = datetime.datetime.now(config.CENTRAL_TIME).date()

    gdate: Optional[datetime.date] = None
    if official_date:
        try:
            gdate = datetime.datetime.strptime(official_date[:10], "%Y-%m-%d").date()
        except Exception:
            gdate = None

    tlabel = (start_time_central or "").strip()
    if tlabel.upper() == "TBD":
        tlabel = ""

    if gdate:
        if gdate == today:
            rel = "Today"
            try:
                t = datetime.datetime.strptime((start_time_central or "").strip(), "%I:%M %p").time()
                if t >= datetime.time(17, 0):
                    rel = "Tonight"
            except Exception:
                pass
            return f"{rel} {tlabel}".strip()
        if gdate == today + datetime.timedelta(days=1):
            return f"Tomorrow {tlabel}".strip()
        if gdate == today - datetime.timedelta(days=1):
            return f"Yesterday {tlabel}".strip()
        return f"{gdate.strftime('%a')} {gdate.month}/{gdate.day} {tlabel}".strip()

    return tlabel or "TBD"

def _rel_label_for_last(official_date: str) -> str:
    """
    For last: prefer Yesterday / Today; else weekday+M/D.
    """
    today = datetime.datetime.now(config.CENTRAL_TIME).date()
    gdate: Optional[datetime.date] = None
    if official_date:
        try:
            gdate = datetime.datetime.strptime(official_date[:10], "%Y-%m-%d").date()
        except Exception:
            gdate = None
    if gdate:
        if gdate == today:                         return "Today"
        if gdate == today - datetime.timedelta(days=1): return "Yesterday"
        if gdate == today + datetime.timedelta(days=1): return "Tomorrow"
        return f"{gdate.strftime('%a')} {gdate.month}/{gdate.day}"
    return "—"

def _status_blurb(game: Dict[str, Any]) -> str:
    gs = (_safe(game, "gameState", default="") or "").upper()
    det = (_safe(game, "detailedState", default="") or _safe(game, "status", "detailedState", default="") or "")
    if gs in ("LIVE", "IN_PROGRESS", "STARTED") or "progress" in det.lower():
        # Period/clock sometimes available under linescore/periodDescriptor
        period = _safe(game, "linescore", "currentPeriodOrdinal", default="") or _safe(game, "periodDescriptor", "number", default="")
        state  = _safe(game, "linescore", "currentPeriodTimeRemaining", default="")
        ptxt = f" {period}" if period else ""
        stxt = f" — {state}" if state else ""
        return f"In Progress{ptxt}{stxt}"
    if gs in ("OFF", "FINAL") or "final" in det.lower():
        return "Final"
    if gs in ("PRE", "FUT", "SCHEDULED") or "sched" in det.lower() or "preview" in det.lower():
        return "Scheduled"
    return det or gs or "—"

def _scores(game: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    a = _safe(game, "awayTeam", "score", default=None) or _safe(game, "away_team", "score", default=None) or _safe(game, "teams", "away", "score", default=None)
    h = _safe(game, "homeTeam", "score", default=None) or _safe(game, "home_team", "score", default=None) or _safe(game, "teams", "home", "score", default=None)
    try: a = int(a)
    except Exception: a = None
    try: h = int(h)
    except Exception: h = None
    return a, h

def _print_header(title: str):
    line = "─" * max(8, len(title))
    print(f"\n{title}\n{line}")

def _print_matchup_line(away_full: str, home_full: str, is_hawks_away: bool, is_hawks_home: bool):
    if is_hawks_away:
        print(f"  Opponent: @ {home_full}")
    elif is_hawks_home:
        print(f"  Opponent: vs. {away_full}")
    else:
        print(f"  Matchup:  {away_full} @ {home_full}")

def _print_score_line(away_abbr: str, home_abbr: str, a: Optional[int], h: Optional[int]):
    if a is None or h is None:
        print(f"  Score:    —")
    else:
        print(f"  Score:    {away_abbr} {a}  —  {home_abbr} {h}")

def _print_block(label: str, game: Optional[Dict[str, Any]], kind: str):
    """
    kind ∈ {'last','live','next','next-home'}
    """
    title = f"{label}: {kind.upper().replace('-', ' ')}"
    _print_header(title)

    if not game:
        print("  (no game)")
        return

    teams = _extract_teams(game)
    if not teams:
        print("  (teams missing)")
        return
    away, home = teams

    away_name = _team_name(away)
    home_name = _team_name(home)
    away_full = _full_name(away_name)
    home_full = _full_name(home_name)
    away_abbr = _abbr(away_full)
    home_abbr = _abbr(home_full)

    is_hawks_away = (away_full == "Chicago Blackhawks" or away_name == "Blackhawks")
    is_hawks_home = (home_full == "Chicago Blackhawks" or home_name == "Blackhawks")

    print(f"  Teams:    {away_full} ({away_abbr}) @ {home_full} ({home_abbr})")
    _print_matchup_line(away_full, home_full, is_hawks_away, is_hawks_home)

    # When label
    official_date = _safe(game, "gameDate", default=_safe(game, "officialDate", default=""))
    start_ct      = _safe(game, "startTimeCentral", default="TBD")
    if kind == "last":
        when = _rel_label_for_last(official_date)
    else:
        when = _rel_label_for_next_or_live(official_date, start_ct)
    print(f"  When:     {when}")

    # Status
    print(f"  Status:   {_status_blurb(game)}")

    # Score (if present)
    a, h = _scores(game)
    _print_score_line(away_abbr, home_abbr, a, h)

# ────────────────────────────────────────────────────────────────────────────
# Main

def main():
    ap = argparse.ArgumentParser(description="Pretty NHL console dump (Chicago Blackhawks).")
    ap.add_argument("--no-last", action="store_true", help="Skip last game")
    ap.add_argument("--no-live", action="store_true", help="Skip live game")
    ap.add_argument("--no-next", action="store_true", help="Skip next game")
    ap.add_argument("--no-next-home", action="store_true", help="Skip next home game")
    args = ap.parse_args()

    if not args.no_last:
        _print_block("Blackhawks", data_fetch.fetch_blackhawks_last_game(), "last")
    if not args.no_live:
        _print_block("Blackhawks", data_fetch.fetch_blackhawks_live_game(), "live")
    if not args.no_next:
        _print_block("Blackhawks", data_fetch.fetch_blackhawks_next_game(), "next")
    if not args.no_next_home:
        _print_block("Blackhawks", data_fetch.fetch_blackhawks_next_home_game(), "next-home")

if __name__ == "__main__":
    main()
