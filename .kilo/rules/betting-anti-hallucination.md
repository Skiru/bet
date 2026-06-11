# Betting Anti-Hallucination Rules

Never invent odds, lineups, injuries, stats, results, standings, kickoff times, or Betclic availability.
Every numeric claim must come from SQLite, a file artifact, or a fetched source.
If a number cannot be verified, write `UNVERIFIED` and lower confidence.
