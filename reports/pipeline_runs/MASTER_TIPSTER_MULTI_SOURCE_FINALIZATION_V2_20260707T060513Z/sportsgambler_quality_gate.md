# Sportsgambler Quality Gate

## Status: RETAINED_CANDIDATE (DO NOT PROMOTE)

Sportsgambler's static BS4 parser has been successfully implemented and tested. We have enforced the **Hard Rule** that index pages must not produce picks (this was verified: the index page run produced exactly 0 picks, and all 17 picks came only from sub-pages/detail links).

However, because the narrative text in Sportsgambler varies in density and reasoning quality, and some events lack explicit reasoning, Sportsgambler fails the semantic threshold of `reasoning_ok >= 80%` required for automatic production shadow promotion.

### Decision
Do NOT promote Sportsgambler. It remains in the registry as `production_candidate_after_robots_terms_fixture_review` and is not included in `CERTIFIED_SHADOW_SOURCE_IDS`.
