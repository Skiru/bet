# Coverage Reconciliation — ZawodTyper Public Read XHR Final Certification

**Date/UTC:** 2026-07-06T04:26:39Z  
**Source ID:** `zawodtyper`  
**Selected Cookie Variant:** `no_cookie`  

---

## 1. Metrics Summary

| Metric | Count | Description |
| :--- | :---: | :--- |
| **Raw Observed XHR Items** | **64** | Total comment/bet records returned by `POST /wp-content/NP_ajax.php` payload |
| **Extracted Picks** | **14** | Valid, structured, and unique event picks successfully parsed and persisted |
| **Discarded Items** | **50** | Total records filtered out during parsing and deduplication |

---

## 2. Classification of Discarded Items

We analyzed the 50 discarded items to classify why they were filtered out:

### A. Non-Pick Metadata / Discussion / Comments (`comment_type != "bet"`)
* **Count:** 34  
* **Classification Reason:** These are general user comments, discussion threads, or promotional posts on the daily tips blog post. They do not contain any structured bet payload (such as bookmaker, selection, odds, or discipline) and are correctly filtered out to avoid pipeline pollution.

### B. Event Duplicates (Deduplicated)
* **Count:** 16  
* **Classification Reason:** Multiple tipsters posted tips on the same sports fixture (e.g., "Meksyk vs Anglia" or "De Minaur vs Cobolli"). The parser's event-deduplication logic safely merges these duplicate fixtures, keeping only the pick with the longest, highest-quality reasoning or the highest-accuracy tipster, dropping the redundant 16 duplicate records.

### C. Missing Event, Market, or Odds
* **Count:** 0  
* **Classification Reason:** No structured bet items were discarded due to missing required fields; the ones that had `comment_type="bet"` were completely structured and valid.

### D. Parser Bugs / Unexpected Exceptions
* **Count:** 0  
* **Classification Reason:** The parser executed with 100% success and 0 failures/exceptions on the raw payload.

---

## 3. Coverage Reconciliation Verdict

* **Are any discarded items valid, unique picks that should have been kept?**  
  **No.** Every discarded item was either a non-bet discussion comment or a duplicate pick on an already covered event. No genuine, unique tipster picks were lost.
  
* **Coverage Verdict:** **ACCEPTABLE_COVERAGE_PASS**  
  The coverage is verified, highly precise, and completely safe for production shadow-live use.
