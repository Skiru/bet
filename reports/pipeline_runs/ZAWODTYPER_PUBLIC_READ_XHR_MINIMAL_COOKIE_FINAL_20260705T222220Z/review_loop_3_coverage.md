# Review Loop 3 Coverage

- XHR called: YES.
- Selected cookie variant: `no_cookie`.
- Raw public XHR items observed during the final live dry run: `64`.
- Extracted evidence picks after parser filtering/deduplication: `14`.
- SQLite persisted picks: `14`.
- Pagination bound respected: entry page + 2 same-origin XHR calls under `--max-pages-per-source 3`.
- Top 10 sample review: all 10 are real sports fixtures/markets; no promo/header/footer garbage detected.
- Coverage note: raw XHR contains many comment-level records. The extractor keeps only `comment_type=bet` entries and deduplicates by event, which explains `64` raw items becoming `14` evidence picks.
- Coverage verdict: PASS.
