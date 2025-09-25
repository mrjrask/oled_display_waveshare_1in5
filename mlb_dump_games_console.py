#!/usr/bin/env python3
"""
mlb_dump_games_console.py

Pretty console dump of MLB game data (Cubs / Sox) from data_fetch.py:
- LAST game   (final score + R/H/E table, date)
- LIVE game   (inning state + partial R/H/E table if available)
- NEXT game   (opponent + scheduled time with Today/Tonight/Tomorrow/Yesterday)

Usage:
  python3 mlb_dump_games_console.py
  python3 mlb_dump_games_console.py --team cubs
  python3 mlb_dump_games_console.py --team sox
"""

from __future__ import annotations
import sys
import argparse
import datetime
from typing import Any, Dict, Optional, Tuple

import data_fetch
import config

# Optional: try to use project helpers for nicer names/abbrevs if available
try:
    from utils import get_team_display_name, get_mlb_abbreviation
except Exception:  # minimal fallbacks
    def get_team_display_name(team) -> str:
        if isinstance(team, dict):
            for k in ("name", "teamName", "fullName", "commonName"):
                v = team.get(k)
                if isinstance(v, dict):
                    v = v.get("default")
                if isinstance(v, str) and v.strip():
                    return v
        return str(team) if team else "UNK"

    def get_mlb_abbreviation(name: str) -> str:
        return name

# ────────────────────────────────────────────────────────────────────────────
# Helpers

def _safe(d: Dict, *keys, default=None):
    """Nested get: _safe(obj, 'a','b','c', default=None)."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default

def _rel_label_for_next(official_date: str, start_time_central: str) -> str:
    """
    'Tonight 7:30 PM', 'Today 1:20 PM', 'Tomorrow 6:05 PM', 'Yesterday 2:10 PM',
    else 'Tue 9/9 1:20 PM' (time omitted if TBD).
    """
    today = datetime.datetime.now(config.CENTRAL_TIME).date()

    # Try YYYY-MM-DD first, else try to slice from gameDate 'YYYY-MM-DDT...'
    gdate: Optional[datetime.date] = None
    if isinstance(official_date, str) and official_date:
        try:
            gdate = datetime.datetime.strptime(official_date[:10], "%Y-%m-%d").date()
        except Exception:
            gdate = None

    # Default time label
    tlabel = (start_time_central or "").strip()
    if tlabel.upper() == "TBD":
        tlabel = ""

    if gdate:
        if gdate == today:
            # Tonight if >= 5:00 PM local
            rel = "Today"
            try:
                t = datetime.datetime.strptime((start_time_central or "").strip(), "%I:%M %p").time()
                if t >= datetime.time(17, 0):
                    rel = "Tonight"
            except Exception:
                pass
            return f"{rel} {tlabel}".strip()
        elif gdate == today + datetime.timedelta(days=1):
            return f"Tomorrow {tlabel}".strip()
        elif gdate == today - datetime.timedelta(days=1):
            # “Yesterday” typically used for last games, but helpful if the “next”
            # window looks back one day due to API windows.
            return f"Yesterday {tlabel}".strip()
        else:
            dow = gdate.strftime("%a")
            md  = f"{gdate.month}/{gdate.day}"
            return f"{dow} {md} {tlabel}".strip()
    # If no date, just return time or TBD
    return tlabel or "TBD"

def _rel_label_for_last(official_date: str) -> str:
    """
    For LAST game we generally show just the date (not time):
    'Yesterday', else 'Mon 9/8'
    """
    today = datetime.datetime.now(config.CENTRAL_TIME).date()
    gdate: Optional[datetime.date] = None
    if isinstance(official_date, str) and official_date:
        try:
            gdate = datetime.datetime.strptime(official_date[:10], "%Y-%m-%d").date()
        except Exception:
            gdate = None
    if gdate:
        if gdate == today:
            return "Today"
        if gdate == today - datetime.timedelta(days=1):
            return "Yesterday"
        if gdate == today + datetime.timedelta(days=1):
            return "Tomorrow"
        return f"{gdate.strftime('%a')} {gdate.month}/{gdate.day}"
    return "—"

def _team_labels(game: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Return (away_name, home_name, away_abbr, home_abbr)."""
    away_team_obj = _safe(game, "teams", "away", "team", default={}) or _safe(game, "awayTeam", default={})
    home_team_obj = _safe(game, "teams", "home", "team", default={}) or _safe(game, "homeTeam", default={})
    away_name = get_team_display_name(away_team_obj)
    home_name = get_team_display_name(home_team_obj)
    return away_name, home_name, get_mlb_abbreviation(away_name), get_mlb_abbreviation(home_name)

def _linescore_cells(game: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    """Return (aR, aH, aE, hR, hH, hE) as strings (or '—')."""
    aR = str(_safe(game, "teams", "away", "score", default="—"))
    hR = str(_safe(game, "teams", "home", "score", default="—"))

    ls  = _safe(game, "linescore", "teams", default={})
    aH  = str(_safe(ls, "away", "hits",   default="—"))
    aE  = str(_safe(ls, "away", "errors", default="—"))
    hH  = str(_safe(ls, "home", "hits",   default="—"))
    hE  = str(_safe(ls, "home", "errors", default="—"))
    return aR, aH, aE, hR, hH, hE

def _status_blurb(game: Dict[str, Any]) -> str:
    st_code  = (_safe(game, "status", "statusCode", default="") or "").upper()
    abs_game = (_safe(game, "status", "abstractGameState", default="") or "").title()
    det      = (_safe(game, "status", "detailedState", default="") or "")
    inning   = f"{_safe(game, 'linescore', 'inningState', default='')}".strip()
    inn_ord  = f"{_safe(game, 'linescore', 'currentInningOrdinal', default='')}".strip()

    if st_code == "I" or "progress" in det.lower() or abs_game == "Live":
        parts = [p for p in (inning, inn_ord) if p]
        return "In Progress" if not parts else " ".join(parts)
    if abs_game in ("Final", "Completed") or st_code in ("F", "O"):
        return "Final"
    if abs_game in ("Preview", "Scheduled") or st_code in ("S",):
        return "Scheduled"
    return abs_game or det or st_code or "—"

def _print_header(title: str):
    line = "─" * max(8, len(title))
    print(f"\n{title}\n{line}")

def _print_boxscore(away_abbr: str, home_abbr: str, aR: str, aH: str, aE: str, hR: str, hH: str, hE: str):
    """
    Small ASCII table. Example:
      AWAY @ HOME
         R  H  E
      CHC 3  7  0
      STL 2  5  1
    """
    hdr = f"{away_abbr} @ {home_abbr}"
    print(f"  {hdr}")
    print("    R  H  E")
    print(f"  {away_abbr:>3} {aR:>2} {aH:>2} {aE:>2}")
    print(f"  {home_abbr:>3} {hR:>2} {hH:>2} {hE:>2}")

def _print_game_block(label: str, game: Optional[Dict[str, Any]], kind: str):
    """
    kind ∈ {'last','live','next'}
    """
    title = f"{label}: {kind.upper()}"
    _print_header(title)

    if not game:
        print("  (no game)")
        return

    away_name, home_name, away_abbr, home_abbr = _team_labels(game)
    aR, aH, aE, hR, hH, hE = _linescore_cells(game)
    status = _status_blurb(game)

    # Headline
    print(f"  {away_name} ({away_abbr}) @ {home_name} ({home_abbr})")
    print(f"  Status: {status}")

    # Time / date blurb
    if kind == "next":
        off_date = _safe(game, "officialDate", default=_safe(game, "gameDate", default=""))
        start_ct = _safe(game, "startTimeCentral", default="TBD")
        print(f"  When:   {_rel_label_for_next(off_date, start_ct)}")
    elif kind == "live":
        off_date = _safe(game, "officialDate", default=_safe(game, "gameDate", default=""))
        start_ct = _safe(game, "startTimeCentral", default="TBD")
        print(f"  When:   {_rel_label_for_next(off_date, start_ct)}")
    else:  # last
        off_date = _safe(game, "officialDate", default=_safe(game, "gameDate", default=""))
        print(f"  Date:   {_rel_label_for_last(off_date)}")

    # Box score (for live we print what we have)
    print()
    _print_boxscore(away_abbr, home_abbr, aR, aH, aE, hR, hH, hE)

# ────────────────────────────────────────────────────────────────────────────
# Main

def main():
    ap = argparse.ArgumentParser(description="Pretty MLB console dump (Cubs/Sox).")
    ap.add_argument("--team", choices=["cubs", "sox", "both"], default="both",
                    help="Which team(s) to show (default: both)")
    args = ap.parse_args()

    to_run = ["cubs", "sox"] if args.team == "both" else [args.team]

    if "cubs" in to_run:
        games = data_fetch.fetch_cubs_games() or {}
        _print_game_block("Cubs", games.get("last_game"), "last")
        _print_game_block("Cubs", games.get("live_game"), "live")
        _print_game_block("Cubs", games.get("next_game"), "next")

    if "sox" in to_run:
        games = data_fetch.fetch_sox_games() or {}
        _print_game_block("Sox", games.get("last_game"), "last")
        _print_game_block("Sox", games.get("live_game"), "live")
        _print_game_block("Sox", games.get("next_game"), "next")

if __name__ == "__main__":
    main()
