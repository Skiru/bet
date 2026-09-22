"""Open the bridge's browser windows with the background throttling turned off.

    python scripts/sofa/launch_bridge_browser.py [--windows 5]

Why this exists
---------------
The bridge's throughput was never limited by Sofascore, by the network, or by
the pipeline. It was limited by one line in the userscript:

    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

`pace()` waits on that to hold MIN_INTERVAL_MS = 350. Chrome clamps setTimeout
in a *hidden* page to >=1000 ms, and escalates to one wake per minute after
five minutes of intensive throttling. So a tab in the background does not run
at its designed 2.86 req/s - it runs at roughly 1, and the two clamped ticks
per job (pull -> fetch -> push) land exactly on the slow mode measured over
80,964 live requests:

    fast mode  p50   175 ms   (15,949 requests)
    slow mode  p50 1,997 ms   (10,544 requests, p10 1,889 / p90 2,097)

That tight cluster is a clamped timer, not a network - a network does not
produce a 200 ms-wide band around a round number.

The workaround used to be "keep three windows visible and non-overlapping",
which costs the operator their screen and silently degrades the moment
anything covers a window. These flags remove the cause instead, so the windows
can sit in the background, minimised, on another desktop - wherever.

    --disable-background-timer-throttling   the 1 s clamp on hidden pages
    --disable-backgrounding-occluded-windows  a covered window counts as hidden
    --disable-renderer-backgrounding        deprioritising the whole renderer

MIN_INTERVAL_MS is NOT touched and must never be. This does not make a tab
faster than it was designed to be; it makes a background tab as fast as a
visible one already was. Capacity still comes from opening more windows.

The profile
-----------
Whichever of the operator's real Chrome profiles already has Tampermonkey, so
there is nothing to install twice. A dedicated profile was the first design and
was wrong: Tampermonkey plus the userscript would have to be set up again, and
a profile cannot simply be copied - Chrome signs the extension entries in
`Secure Preferences` with a MAC tied to the profile, so a copied extension
arrives disabled.

The cold-start requirement
--------------------------
These are process-creation flags. If Chrome is already running, launching it
again does NOT create a process - it messages the existing one, which opens the
window and silently drops every flag. The tab is then still clamped and nothing
says so. That is the same shape of silent failure as the deleted latency check,
so this script refuses to launch instead of producing a window that looks right
and runs at a fifth of the speed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Chrome counts a window as backgrounded when it is not focused, and as
# occluded when another window covers it. Both paths lead to the same timer
# clamp, so all three flags are needed to make "in the background" mean
# "still running at full speed".
ANTI_THROTTLE_FLAGS = [
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]

# Not throttling-related, just noise suppression on a dedicated profile.
PROFILE_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
]

TARGET_URL = "https://www.sofascore.com/"

TAMPERMONKEY_ID = "dhdgffkkebhmkfjojejmpbldmpobfkfo"

# One in-flight job per tab at MIN_INTERVAL_MS = 350 is 2.86 req/s per window,
# so five windows is ~14.3 req/s. The bucket in SofaConfig has to sit ABOVE
# that or the tabs go idle between jobs and pay a poll cycle - which is the
# other half of the same bug this script fixes.
DEFAULT_WINDOWS = 5

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_chrome() -> str | None:
    for path in CHROME_PATHS:
        if Path(path).exists():
            return path
    return shutil.which("google-chrome") or shutil.which("chromium")


def chrome_user_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"


def find_tampermonkey_profile(user_data: Path) -> str | None:
    """Which profile directory has the extension the bridge depends on.

    Without this the script would happily launch a profile where the userscript
    does not exist, and the bridge would look merely idle.
    """
    if not user_data.exists():
        return None
    candidates = sorted(
        p
        for p in user_data.iterdir()
        if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile "))
    )
    for profile in candidates:
        if (profile / "Extensions" / TAMPERMONKEY_ID).exists():
            return profile.name
    return None


def chrome_is_running() -> bool:
    """A running Chrome makes every flag below a no-op, silently."""
    result = subprocess.run(
        ["pgrep", "-f", "Google Chrome.app/Contents/MacOS/Google Chrome"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def build_command(
    chrome: str, profile: Path, windows: int, profile_name: str | None = None
) -> list[list[str]]:
    """One process for the first window, then one --new-window per extra.

    Chrome collapses repeated URLs on the command line into tabs of a single
    window, and tabs of one window do not help: only the active tab of a
    window is visible, so N tabs in one window is one working tab. Separate
    --new-window invocations against the same profile give N real windows.
    """
    base = [chrome, f"--user-data-dir={profile}", *ANTI_THROTTLE_FLAGS, *PROFILE_FLAGS]
    if profile_name:
        base.append(f"--profile-directory={profile_name}")
    commands = [[*base, TARGET_URL]]
    for _ in range(windows - 1):
        commands.append([*base, "--new-window", TARGET_URL])
    return commands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--windows",
        type=int,
        default=DEFAULT_WINDOWS,
        help=f"how many sofascore.com windows to open (default {DEFAULT_WINDOWS})",
    )
    args = parser.parse_args()

    if args.windows < 1:
        print("--windows must be at least 1", file=sys.stderr)
        return 2

    chrome = find_chrome()
    if chrome is None:
        print("FAIL  no Chrome or Chromium found in the usual places:", file=sys.stderr)
        for path in CHROME_PATHS:
            print(f"      {path}", file=sys.stderr)
        return 2

    user_data = chrome_user_data_dir()
    profile_name = find_tampermonkey_profile(user_data)
    if profile_name is None:
        err = sys.stderr
        print(f"FAIL  no Chrome profile under {user_data} has Tampermonkey", file=err)
        print(f"      (looked for Extensions/{TAMPERMONKEY_ID})", file=err)
        print("      Install Tampermonkey and the userscript first.", file=err)
        return 2

    # Process-creation flags are ignored by an already-running Chrome, which
    # would leave the tab clamped with nothing saying so.
    if chrome_is_running():
        err = sys.stderr
        print("FAIL  Chrome is already running, so the anti-throttling flags", file=err)
        print("      would be silently ignored - a new invocation only", file=err)
        print("      messages the existing process. Quit Chrome completely", file=err)
        print("      (Cmd+Q, not just closing the windows) and re-run this.", file=err)
        return 1

    commands = build_command(chrome, user_data, args.windows, profile_name)
    for index, command in enumerate(commands):
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # The first invocation creates the browser process; the --new-window
        # ones attach to it and race it if they arrive too early.
        if index == 0:
            time.sleep(4.0)
        else:
            time.sleep(0.6)

    print(f"OK    launched {args.windows} window(s) with background throttling off")
    print(f"      profile: {profile_name}  (Tampermonkey found here)")
    print("      These windows do NOT need to stay on top, visible, or")
    print("      non-overlapping. That was a workaround for the timer clamp")
    print("      these flags remove. Minimise them if you like.")
    print()
    print("Verify, and read the round-trip line rather than just ok:true:")
    print("  .venv/bin/python scripts/sofa/check_bridge.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
