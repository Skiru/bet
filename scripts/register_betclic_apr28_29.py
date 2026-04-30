#!/usr/bin/env python3
"""Register Betclic bet slips from April 28-29, 2026 screenshots into betclic_bets_history.json."""
import json
import os

HISTORY_FILE = os.path.join(os.path.dirname(__file__), '..', 'betting', 'data', 'betclic_bets_history.json')

new_bets = [
    # === Screenshot 12: AKO(2) WON - 28.04.2026 10:12 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f06bd81665e1956a419178",
        "coupon_status": "won",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Wygrane",
        "leg_status_icons": ["won", "won"],
        "total_odds": 1.65,
        "stake_pln": 1.07,
        "winnings_pln": 1.55,
        "tax_free_payout_pln": 1.76,
        "footer_ref": "69f06bd81665e1956a419178",
        "placed_date": "28.04.2026 10:12",
        "legs": [
            {
                "sport": "tennis",
                "selection": "Poniżej 21,5",
                "leg_status": "won",
                "market": "Łączna liczba gemów",
                "odds": 1.22,
                "home": "Jannik Sinner",
                "away": "Cameron Norrie",
                "score_home": "6 7",
                "score_away": "2 5",
                "score": "6-2, 7-5",
                "event_time": "Wt. 28/04 11:00"
            },
            {
                "sport": "snooker",
                "selection": "Powyżej 20,5",
                "leg_status": "won",
                "market": "Łączna liczba frejmów",
                "odds": 1.35,
                "home": "Wu Yize",
                "away": "Hossein Vafaei",
                "score_home": "13",
                "score_away": "8",
                "score": "13-8",
                "event_time": "Wt. 28/04 15:30"
            }
        ],
        "pnl_pln": 0.69
    },
    # === Screenshot 3: AKO(2) WON - 28.04.2026 13:49 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f09ed200c447153a2b4580",
        "coupon_status": "won",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Wygrane",
        "leg_status_icons": ["won", "won"],
        "total_odds": 2.18,
        "stake_pln": 2.0,
        "winnings_pln": 3.84,
        "tax_free_payout_pln": 4.36,
        "footer_ref": "69f09ed200c447153a2b4580",
        "placed_date": "28.04.2026 13:49",
        "legs": [
            {
                "sport": "tennis",
                "selection": "Powyżej 21,5",
                "leg_status": "won",
                "market": "Łączna liczba gemów",
                "odds": 1.64,
                "home": "Stefanos Tsitsipas",
                "away": "Casper Ruud",
                "score_home": "7 6 6",
                "score_away": "6 7 7",
                "score": "7-6, 6-7, 6-7",
                "event_time": "Wt. 28/04 14:25"
            },
            {
                "sport": "snooker",
                "selection": "Powyżej 20,5",
                "leg_status": "won",
                "market": "Łączna liczba frejmów",
                "odds": 1.33,
                "home": "John Higgins",
                "away": "Neil Robertson",
                "score_home": "13",
                "score_away": "10",
                "score": "13-10",
                "event_time": "Wt. 28/04 15:30"
            }
        ],
        "pnl_pln": 2.36
    },
    # === Screenshot 2: AKO(2) WON - 28.04.2026 14:50 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f0ad2786b09edd924aec5d",
        "coupon_status": "won",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Wygrane",
        "leg_status_icons": ["won", "won"],
        "total_odds": 1.86,
        "stake_pln": 3.0,
        "winnings_pln": 4.91,
        "tax_free_payout_pln": 5.58,
        "footer_ref": "69f0ad2786b09edd924aec5d",
        "placed_date": "28.04.2026 14:50",
        "legs": [
            {
                "sport": "tennis",
                "selection": "Powyżej 21,5",
                "leg_status": "won",
                "market": "Łączna liczba gemów",
                "odds": 1.40,
                "home": "Stefanos Tsitsipas",
                "away": "Casper Ruud",
                "score_home": "7 6 6",
                "score_away": "6 7 7",
                "score": "7-6, 6-7, 6-7",
                "event_time": "Wt. 28/04 14:25"
            },
            {
                "sport": "snooker",
                "selection": "Powyżej 20,5",
                "leg_status": "won",
                "market": "Łączna liczba frejmów",
                "odds": 1.33,
                "home": "John Higgins",
                "away": "Neil Robertson",
                "score_home": "13",
                "score_away": "10",
                "score": "13-10",
                "event_time": "Wt. 28/04 15:30"
            }
        ],
        "pnl_pln": 2.58
    },
    # === Screenshot 1: AKO(4) WON - Night session ~28.04.2026 ===
    {
        "bet_type": "AKO (4)",
        "expected_legs": 4,
        "ref_id": "UNKNOWN_NIGHT_AKO4_20260429",
        "coupon_status": "won",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Wygrane",
        "leg_status_icons": ["won", "won", "won", "won"],
        "total_odds": 10.03,
        "stake_pln": 1.79,
        "winnings_pln": 15.85,
        "tax_free_payout_pln": 17.96,
        "footer_ref": "UNKNOWN_NIGHT_AKO4_20260429",
        "placed_date": "28.04.2026 23:00",
        "legs": [
            {
                "sport": "baseball",
                "selection": "Powyżej 9,5",
                "leg_status": "won",
                "market": "Liczba Runs",
                "odds": 1.87,
                "home": "Cincinnati Reds",
                "away": "Colorado Rockies",
                "score_home": "2",
                "score_away": "13",
                "score": "2-13",
                "event_time": "Dzisiaj 00:40"
            },
            {
                "sport": "basketball",
                "selection": "Powyżej 216,5",
                "leg_status": "won",
                "market": "Suma punktów",
                "odds": 1.66,
                "home": "Cleveland Cavaliers",
                "away": "Toronto Raptors",
                "score_home": "125",
                "score_away": "120",
                "score": "125-120",
                "event_time": "Dzisiaj 01:30"
            },
            {
                "sport": "basketball",
                "selection": "Poniżej 207,5",
                "leg_status": "won",
                "market": "Suma punktów",
                "odds": 1.89,
                "home": "LA Lakers",
                "away": "Houston Rockets",
                "score_home": "93",
                "score_away": "99",
                "score": "93-99",
                "event_time": "Dzisiaj 04:00"
            },
            {
                "sport": "hockey",
                "selection": "Powyżej 5,5",
                "leg_status": "won",
                "market": "Liczba goli (Dogrywka i rzuty karne są wliczane do zakładu)",
                "odds": 1.71,
                "home": "Vegas Golden Knights",
                "away": "Utah Mammoth",
                "score_home": "4",
                "score_away": "4",
                "score": "4-4 (OT)",
                "event_time": "Dzisiaj"
            }
        ],
        "pnl_pln": 16.17,
        "notes": "Ref ID not visible in screenshot. Night session US sports. VGK-Utah went to OT, 8+ goals already won."
    },
    # === Screenshot 14: AKO(3) LOST - 29.04.2026 13:44 ===
    {
        "bet_type": "AKO (3)",
        "expected_legs": 3,
        "ref_id": "69f1ef298811544b695d3aa7",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["lost", "won", "lost"],
        "total_odds": 4.70,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f1ef298811544b695d3aa7",
        "placed_date": "29.04.2026 13:44",
        "legs": [
            {
                "sport": "football",
                "selection": "Powyżej 2,5",
                "leg_status": "lost",
                "market": "Gole Powyżej/Poniżej",
                "odds": 1.77,
                "home": "Inter Turku",
                "away": "HJK Helsinki",
                "score_home": "1",
                "score_away": "1",
                "score": "1-1",
                "event_time": "Wczoraj 18:00"
            },
            {
                "sport": "football",
                "selection": "Powyżej 4,5",
                "leg_status": "won",
                "market": "Rzuty rożne Arsenal (razem z dogrywką)",
                "odds": 1.62,
                "home": "Atletico Madryt",
                "away": "Arsenal",
                "score_home": "1",
                "score_away": "1",
                "score": "1-1",
                "event_time": "Wczoraj 21:00"
            },
            {
                "sport": "hockey",
                "selection": "Powyżej 2,5",
                "leg_status": "lost",
                "market": "Pittsburgh Penguins Liczba goli (Dogrywka i rzuty karne są wliczane do zakładu)",
                "odds": 1.64,
                "home": "Philadelphia Flyers",
                "away": "Pittsburgh Penguins",
                "score_home": "1",
                "score_away": "0",
                "score": "1-0",
                "event_time": "Dzisiaj 01:30"
            }
        ],
        "pnl_pln": -1.0
    },
    # === Screenshot 10: AKO(2) LOST - 29.04.2026 15:00 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f200fe7042a970ef49be54",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["lost", "lost"],
        "total_odds": 1.89,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f200fe7042a970ef49be54",
        "placed_date": "29.04.2026 15:00",
        "legs": [],
        "pnl_pln": -1.0,
        "notes": "Legs not visible in screenshot (collapsed view). Only summary visible: AKO(2), 2 legs lost, odds 1.89, stake 1.00 zł."
    },
    # === Screenshot 9: AKO(2) LOST - 29.04.2026 15:01 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f20130f720ae95e98ce57d",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["won", "lost"],
        "total_odds": 2.38,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f20130f720ae95e98ce57d",
        "placed_date": "29.04.2026 15:01",
        "legs": [
            {
                "sport": "football",
                "selection": "Powyżej 2,5",
                "leg_status": "won",
                "market": "Gole Powyżej/Poniżej",
                "odds": 1.49,
                "home": "Den Bosch",
                "away": "Almere City",
                "score_home": "2",
                "score_away": "3",
                "score": "2-3",
                "event_time": "Wczoraj 18:45"
            },
            {
                "sport": "football",
                "selection": "Powyżej 4,5",
                "leg_status": "lost",
                "market": "Rzuty rożne Arsenal (razem z dogrywką)",
                "odds": 1.60,
                "home": "Atletico Madryt",
                "away": "Arsenal",
                "score_home": "1",
                "score_away": "1",
                "score": "1-1",
                "event_time": "Wczoraj 21:00"
            }
        ],
        "pnl_pln": -1.0
    },
    # === Screenshot 4: AKO(2) LOST - 29.04.2026 15:02 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f201594dc66992fdcb94e9",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["lost", "lost"],
        "total_odds": 1.95,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f201594dc66992fdcb94e9",
        "placed_date": "29.04.2026 15:02",
        "legs": [
            {
                "sport": "football",
                "selection": "Powyżej 5,5",
                "leg_status": "lost",
                "market": "Rzuty rożne (bez dogrywki) - Sporting Lizbona",
                "odds": 1.18,
                "home": "Sporting Lizbona",
                "away": "Tondela",
                "score_home": "2",
                "score_away": "2",
                "score": "2-2",
                "event_time": "Wczoraj 21:15"
            },
            {
                "sport": "hockey",
                "selection": "Powyżej 2,5",
                "leg_status": "lost",
                "market": "Pittsburgh Penguins Liczba goli (Dogrywka i rzuty karne są wliczane do zakładu)",
                "odds": 1.65,
                "home": "Philadelphia Flyers",
                "away": "Pittsburgh Penguins",
                "score_home": "1",
                "score_away": "0",
                "score": "1-0",
                "event_time": "Dzisiaj 01:30"
            }
        ],
        "pnl_pln": -1.0
    },
    # === Screenshot 6: AKO(2) LOST - 29.04.2026 15:04 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f201d68811544b695dfe06",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["lost", "lost"],
        "total_odds": 2.23,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f201d68811544b695dfe06",
        "placed_date": "29.04.2026 15:04",
        "legs": [
            {
                "sport": "football",
                "selection": "Powyżej 4,5",
                "leg_status": "lost",
                "market": "Rzuty rożne (bez dogrywki) - Tromsø IL",
                "odds": 1.42,
                "home": "Tromsø IL",
                "away": "Brann",
                "score_home": "0",
                "score_away": "5",
                "score": "0-5",
                "event_time": "Wczoraj 19:00"
            },
            {
                "sport": "tennis",
                "selection": "Powyżej 21,5",
                "leg_status": "lost",
                "market": "Łączna liczba gemów",
                "odds": 1.57,
                "home": "Arthur Fils",
                "away": "Jiri Lehecka",
                "score_home": "6 6",
                "score_away": "3 4",
                "score": "6-3, 6-4",
                "event_time": "Wczoraj 21:50"
            }
        ],
        "pnl_pln": -1.0
    },
    # === Screenshot 15: AKO(2) LOST - 29.04.2026 15:05 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f2020bf720ae95e98cefec",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["lost", "won"],
        "total_odds": 4.16,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f2020bf720ae95e98cefec",
        "placed_date": "29.04.2026 15:05",
        "legs": [
            {
                "sport": "volleyball",
                "selection": "Poniżej 3,5",
                "leg_status": "lost",
                "market": "Suma Setów Powyżej/Poniżej",
                "odds": 3.20,
                "home": "LUK Lublin",
                "away": "Warta Zawiercie",
                "score_home": "21 25 25 29",
                "score_away": "25 21 23 27",
                "score": "3-1",
                "event_time": "Wczoraj 17:30"
            },
            {
                "sport": "volleyball",
                "selection": "Powyżej 3,5",
                "leg_status": "won",
                "market": "Suma Setów Powyżej/Poniżej",
                "odds": 1.30,
                "home": "SVG Luneburge",
                "away": "Berlin Volley",
                "score_home": "20 19 25 21",
                "score_away": "25 25 18 25",
                "score": "1-3",
                "event_time": "Wczoraj 20:00"
            }
        ],
        "pnl_pln": -1.0
    },
    # === Screenshot 11: AKO(3) LOST - 29.04.2026 15:07 ===
    {
        "bet_type": "AKO (3)",
        "expected_legs": 3,
        "ref_id": "69f20291f720ae95e98cf689",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["won", "lost", "lost"],
        "total_odds": 2.58,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f20291f720ae95e98cf689",
        "placed_date": "29.04.2026 15:07",
        "legs": [
            {
                "sport": "volleyball",
                "selection": "Powyżej 3,5",
                "leg_status": "won",
                "market": "Suma Setów Powyżej/Poniżej",
                "odds": 1.30,
                "home": "SVG Luneburge",
                "away": "Berlin Volley",
                "score_home": "20 19 25 21",
                "score_away": "25 25 18 25",
                "score": "1-3",
                "event_time": "Wczoraj 20:00"
            },
            {
                "sport": "volleyball",
                "selection": "KS Rzeszów K. -3,5",
                "leg_status": "lost",
                "market": "Handicap punktowy",
                "odds": 1.47,
                "home": "KS Rzeszów K.",
                "away": "Budowlani Łódź K.",
                "score_home": "23 18 25 23",
                "score_away": "25 25 22 25",
                "score": "1-3",
                "event_time": "Wczoraj 20:00"
            },
            {
                "sport": "football",
                "selection": "Powyżej 8,5",
                "leg_status": "lost",
                "market": "Suma rzutów rożnych (razem z dogrywką)",
                "odds": 1.35,
                "home": "Atletico Madryt",
                "away": "Arsenal",
                "score_home": "1",
                "score_away": "1",
                "score": "1-1",
                "event_time": "Wczoraj 21:00"
            }
        ],
        "pnl_pln": -1.0
    },
    # === Screenshot 5: AKO(2) LOST - 29.04.2026 15:09 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f202fcf720ae95e98cfb16",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["won", "lost"],
        "total_odds": 2.29,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f202fcf720ae95e98cfb16",
        "placed_date": "29.04.2026 15:09",
        "legs": [
            {
                "sport": "tennis",
                "selection": "Poniżej 22,5",
                "leg_status": "won",
                "market": "Łączna liczba gemów",
                "odds": 1.46,
                "home": "Jannik Sinner",
                "away": "Rafael Jodar",
                "score_home": "6 7",
                "score_away": "2 6",
                "score": "6-2, 7-6",
                "event_time": "Wczoraj 16:00"
            },
            {
                "sport": "tennis",
                "selection": "Powyżej 21,5",
                "leg_status": "lost",
                "market": "Łączna liczba gemów",
                "odds": 1.57,
                "home": "Arthur Fils",
                "away": "Jiri Lehecka",
                "score_home": "6 6",
                "score_away": "3 4",
                "score": "6-3, 6-4",
                "event_time": "Wczoraj 21:50"
            }
        ],
        "pnl_pln": -1.0
    },
    # === Screenshot 13: AKO(2) WON - 29.04.2026 15:10 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f2034df720ae95e98cff39",
        "coupon_status": "won",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Wygrane",
        "leg_status_icons": ["won", "won"],
        "total_odds": 1.97,
        "stake_pln": 1.0,
        "winnings_pln": 1.73,
        "tax_free_payout_pln": 1.97,
        "footer_ref": "69f2034df720ae95e98cff39",
        "placed_date": "29.04.2026 15:10",
        "legs": [
            {
                "sport": "volleyball",
                "selection": "Powyżej 3,5",
                "leg_status": "won",
                "market": "Suma Setów Powyżej/Poniżej",
                "odds": 1.27,
                "home": "LUK Lublin",
                "away": "Warta Zawiercie",
                "score_home": "21 25 25 29",
                "score_away": "25 21 23 27",
                "score": "3-1",
                "event_time": "Wczoraj 17:30"
            },
            {
                "sport": "football",
                "selection": "Pcimianka Pcim",
                "leg_status": "won",
                "market": "Wynik meczu (z wyłączeniem dogrywki)",
                "odds": 1.55,
                "home": "Pcimianka Pcim",
                "away": "MKS Trzebinia",
                "score_home": "",
                "score_away": "",
                "score": "",
                "event_time": "Wczoraj 19:30"
            }
        ],
        "pnl_pln": 0.97
    },
    # === Screenshot 8: AKO(2) LOST - 29.04.2026 18:39 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f234438811544b695f865f",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["lost", "lost"],
        "total_odds": 2.52,
        "stake_pln": 2.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f234438811544b695f865f",
        "placed_date": "29.04.2026 18:39",
        "legs": [
            {
                "sport": "football",
                "selection": "Powyżej 4,5",
                "leg_status": "lost",
                "market": "Rzuty rożne Arsenal (razem z dogrywką)",
                "odds": 1.52,
                "home": "Atletico Madryt",
                "away": "Arsenal",
                "score_home": "1",
                "score_away": "1",
                "score": "1-1",
                "event_time": "Wczoraj 21:00"
            },
            {
                "sport": "basketball",
                "selection": "Poniżej 213,5",
                "leg_status": "lost",
                "market": "Suma punktów",
                "odds": 1.66,
                "home": "Detroit Pistons",
                "away": "Orlando Magic",
                "score_home": "116",
                "score_away": "109",
                "score": "116-109",
                "event_time": "Dzisiaj 01:00"
            }
        ],
        "pnl_pln": -2.0
    },
    # === Screenshot 7: AKO(2) LOST - 29.04.2026 20:47 ===
    {
        "bet_type": "AKO (2)",
        "expected_legs": 2,
        "ref_id": "69f25244f720ae95e98f3f78",
        "coupon_status": "lost",
        "is_ended": True,
        "is_betbuilder": False,
        "is_combined": True,
        "status_label": "Przegrany",
        "leg_status_icons": ["lost", "won"],
        "total_odds": 2.47,
        "stake_pln": 1.0,
        "winnings_pln": 0.0,
        "footer_ref": "69f25244f720ae95e98f3f78",
        "placed_date": "29.04.2026 20:47",
        "legs": [
            {
                "sport": "football",
                "selection": "Powyżej 9,5",
                "leg_status": "lost",
                "market": "Suma rzutów rożnych (razem z dogrywką)",
                "odds": 1.45,
                "home": "Atletico Madryt",
                "away": "Arsenal",
                "score_home": "1",
                "score_away": "1",
                "score": "1-1",
                "event_time": "Wczoraj 21:00"
            },
            {
                "sport": "hockey",
                "selection": "Powyżej 5,5",
                "leg_status": "won",
                "market": "Liczba goli (Dogrywka i rzuty karne są wliczane do zakładu)",
                "odds": 1.70,
                "home": "Vegas Golden Knights",
                "away": "Utah Mammoth",
                "score_home": "4",
                "score_away": "4",
                "score": "4-4 (OT)",
                "event_time": "Dzisiaj"
            }
        ],
        "pnl_pln": -1.0
    }
]


def main():
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    existing_refs = {b.get('ref_id', '') for b in data}
    added = 0
    skipped = 0

    for bet in new_bets:
        if bet['ref_id'] in existing_refs:
            print(f"SKIP (duplicate): {bet['ref_id']} - {bet['placed_date']}")
            skipped += 1
        else:
            data.append(bet)
            existing_refs.add(bet['ref_id'])
            added += 1
            status = bet['coupon_status'].upper()
            pnl = bet['pnl_pln']
            print(f"ADD: {bet['ref_id']} - {bet['placed_date']} - {status} - PnL: {pnl:+.2f} zł")

    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n=== Summary ===")
    print(f"Added: {added}, Skipped: {skipped}")
    print(f"Total bets in history: {len(data)}")

    # Quick PnL summary for these bets
    total_stake = sum(b['stake_pln'] for b in new_bets)
    total_pnl = sum(b['pnl_pln'] for b in new_bets)
    wins = sum(1 for b in new_bets if b['coupon_status'] == 'won')
    losses = sum(1 for b in new_bets if b['coupon_status'] == 'lost')
    print(f"\nApril 28-29 session:")
    print(f"  Coupons: {len(new_bets)} ({wins}W / {losses}L)")
    print(f"  Total staked: {total_stake:.2f} zł")
    print(f"  Net PnL: {total_pnl:+.2f} zł")
    print(f"  ROI: {(total_pnl/total_stake)*100:+.1f}%")


if __name__ == '__main__':
    main()
