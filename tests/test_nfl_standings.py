import pytest

from screens.nfl_standings import (
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


@pytest.fixture
def grouped_payload():
    return {
        "children": [
            {
                "name": "NFL",
                "standings": {
                    "entriesByGroup": [
                        {
                            "group": {
                                "name": "AFC East",
                                "parent": {"name": "American Football Conference"},
                            },
                            "entries": [
                                {
                                    "team": {"abbreviation": "BUF"},
                                    "stats": [
                                        {"name": "wins", "value": 13},
                                        {"name": "losses", "value": 4},
                                        {"name": "ties", "value": 0},
                                        {"name": "playoffSeed", "value": 1},
                                    ],
                                },
                                {
                                    "team": {"abbreviation": "MIA"},
                                    "stats": [
                                        {"name": "wins", "value": 11},
                                        {"name": "losses", "value": 6},
                                        {"name": "ties", "value": 0},
                                        {"name": "playoffSeed", "value": 5},
                                    ],
                                },
                            ],
                        },
                        {
                            "group": {
                                "name": "NFC North",
                                "parent": {"name": "National Football Conference"},
                            },
                            "entries": [
                                {
                                    "team": {
                                        "abbreviation": "DET",
                                        "standingSummary": "1st in NFC North",
                                    },
                                    "stats": [
                                        {"name": "wins", "value": 12},
                                        {"name": "losses", "value": 5},
                                        {"name": "ties", "value": 0},
                                        {"name": "playoffSeed", "value": 2},
                                    ],
                                },
                            ],
                        },
                    ]
                },
            }
        ]
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


def test_parse_standings_handles_entries_by_group(grouped_payload):
    standings = _parse_standings(grouped_payload)

    afc_east = standings[CONFERENCE_AFC_KEY]["AFC East"]
    nfc_north = standings[CONFERENCE_NFC_KEY]["NFC North"]

    assert [team["abbr"] for team in afc_east] == ["BUF", "MIA"]
    assert afc_east[0]["wins"] == 13
    assert afc_east[1]["losses"] == 6

    assert [team["abbr"] for team in nfc_north] == ["DET"]
    assert nfc_north[0]["wins"] == 12
