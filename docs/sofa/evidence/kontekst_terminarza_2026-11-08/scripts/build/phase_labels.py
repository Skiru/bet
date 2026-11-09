"""D10: as-of season phase label per football event (season_phase.phases_by_event
on the copy's history, awarded excluded) -> phase_labels.pkl {eid: label}."""
import pickle
import sys
from pathlib import Path

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa import season_phase as sp  # noqa: E402
from scripts.sofa.measure_season_phase import load_history  # noqa: E402

D = REPO / "data/refit_2026-11-08_schedule"
h = load_history(D / "cache/football_history.pkl", awarded_out=True)
lab = {int(k): v for k, v in sp.phases_by_event(h).items()}
(D / "phase_labels.pkl").write_bytes(pickle.dumps(lab))
from collections import Counter  # noqa: E402
print(len(lab), Counter(lab.values()))
