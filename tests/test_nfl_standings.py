import pytest

from nfl_standings import (
    CONFERENCE_AFC_KEY,
    CONFERENCE_NFC_KEY,
    _parse_standings,
)


@pytest.fixture
def summary_payload():
    return {
        "standings": {
            "entries": [
                {
                    "team": {
                        "abbreviation": "BUF",
                        "standingSummary": "1st in AFC East",
                    },
                    "stats": [
                        {"name": "wins", "value": 11},
                        {"name": "losses", "value": 6},
                        {"name": "ties", "value": 0},
                        {"name": "playoffSeed", "value": 2},
                    ],
                },
                {
                    "team": {
                        "abbreviation": "MIA",
                        "standingSummary": "2nd in AFC East",
                    },
                    "stats": [
                        {"name": "wins", "value": 10},
                        {"name": "losses", "value": 7},
                        {"name": "ties", "value": 0},
                        {"name": "playoffSeed", "value": 5},
                    ],
                },
                {
                    "team": {
                        "abbreviation": "PHI",
                        "standingSummary": "1st in NFC East",
                    },
                    "stats": [
                        {"name": "wins", "value": 12},
                        {"name": "losses", "value": 5},
                        {"name": "ties", "value": 0},
                        {"name": "playoffSeed", "value": 1},
                    ],
                },
            ]
        }
    }


def test_parse_standings_uses_standing_summary(summary_payload):
    standings = _parse_standings(summary_payload)

    afc_east = standings[CONFERENCE_AFC_KEY]["AFC East"]
    nfc_east = standings[CONFERENCE_NFC_KEY]["NFC East"]

    assert [team["abbr"] for team in afc_east] == ["BUF", "MIA"]
    assert nfc_east[0]["abbr"] == "PHI"

    # Ensure records were carried over
    assert afc_east[0]["wins"] == 11
    assert afc_east[1]["losses"] == 7
