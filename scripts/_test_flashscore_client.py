"""Integration test for the new FlashscoreClient.

Tests all public methods: get_fixtures, get_fixture_stats, get_h2h, get_match_preview.
"""
import sys
import logging

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)


def test_flashscore_client():
    from bet.api_clients.flashscore import FlashscoreClient

    client = FlashscoreClient()

    try:
        # ── Test 1: get_fixtures ──────────────────────────────────
        print("\n" + "=" * 60, flush=True)
        print("TEST 1: get_fixtures (football)", flush=True)
        print("=" * 60, flush=True)

        fixtures = client.get_fixtures("2026-05-13", sport="football")
        print(f"Total football fixtures: {len(fixtures)}", flush=True)

        if fixtures:
            for f in fixtures[:10]:
                print(f"  {f.competition_name}: {f.home_team_name} vs {f.away_team_name} @ {f.kickoff} [{f.status}]", flush=True)

            # Get a scheduled match ID for further tests
            scheduled = [f for f in fixtures if f.status == "scheduled" and f.external_id]
            if scheduled:
                test_event_id = scheduled[0].external_id
                print(f"\nUsing event ID for further tests: {test_event_id}", flush=True)
            else:
                test_event_id = fixtures[0].external_id
                print(f"\nUsing first event ID: {test_event_id}", flush=True)
        else:
            print("  No fixtures found!", flush=True)
            test_event_id = None

        # ── Test 2: get_fixtures for other sports ─────────────────
        for sport in ["basketball", "hockey", "tennis"]:
            print(f"\n  {sport}:", end=" ", flush=True)
            sport_fixtures = client.get_fixtures("2026-05-13", sport=sport)
            print(f"{len(sport_fixtures)} fixtures", flush=True)
            if sport_fixtures:
                for f in sport_fixtures[:3]:
                    print(f"    {f.competition_name}: {f.home_team_name} vs {f.away_team_name}", flush=True)

        # ── Test 3: get_match_preview ─────────────────────────────
        if test_event_id:
            print("\n" + "=" * 60, flush=True)
            print(f"TEST 3: get_match_preview ({test_event_id})", flush=True)
            print("=" * 60, flush=True)

            preview = client.get_match_preview(test_event_id)
            if preview:
                print(f"  Home: {preview.get('home', '?')}", flush=True)
                print(f"  Away: {preview.get('away', '?')}", flush=True)
                print(f"  Tournament: {preview.get('tournament', '?')}", flush=True)
                print(f"  Venue: {preview.get('venue', '?')}", flush=True)
                print(f"  Form Home: {preview.get('form_home', [])}", flush=True)
                print(f"  Form Away: {preview.get('form_away', [])}", flush=True)
                print(f"  H2H: {len(preview.get('h2h', []))} matches", flush=True)
                for h in preview.get("h2h", [])[:3]:
                    print(f"    {h.get('date','')} {h['home']} {h.get('score_home','?')}-{h.get('score_away','?')} {h['away']}", flush=True)

        # ── Test 4: get_h2h ───────────────────────────────────────
        if test_event_id:
            print("\n" + "=" * 60, flush=True)
            print(f"TEST 4: get_h2h ({test_event_id})", flush=True)
            print("=" * 60, flush=True)

            h2h = client.get_h2h(test_event_id, "")
            print(f"  H2H matches: {len(h2h)}", flush=True)
            for h in h2h[:5]:
                print(f"    {h.get('date','')} {h['home']} {h.get('score_home','?')}-{h.get('score_away','?')} {h['away']}", flush=True)

        # ── Test 5: get_fixture_stats ─────────────────────────────
        if test_event_id:
            print("\n" + "=" * 60, flush=True)
            print(f"TEST 5: get_fixture_stats ({test_event_id})", flush=True)
            print("=" * 60, flush=True)

            stats = client.get_fixture_stats(test_event_id)
            print(f"  Stats categories: {len(stats)}", flush=True)
            for s in stats[:10]:
                print(f"    {s.get('category','?')}: {s.get('home','?')} - {s.get('away','?')}", flush=True)

            if not stats:
                print("  (No stats — likely a scheduled match, not finished yet)", flush=True)

        print("\n" + "=" * 60, flush=True)
        print("ALL TESTS COMPLETE", flush=True)
        print("=" * 60, flush=True)

    finally:
        client.close()


if __name__ == "__main__":
    test_flashscore_client()
