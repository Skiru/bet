#!/usr/bin/env python3
"""Regenerate golden/off_identical_head.json from an ARCHIVE of the commit the
2026-10-08 change set started from (not the working tree):

    d=$(mktemp -d) && git archive <commit> src scripts config tests | tar -x -C $d
    cp tests/sofa/off_scenarios.py $d/tests/sofa/ && cp tests/sofa/golden/side_correlations_input.json $d/tests/sofa/golden/
    (cd $d && PYTHONPATH=src:. <repo>/.venv/bin/python tests/sofa/golden/make_off_goldens.py <repo>/tests/sofa/golden/off_identical_head.json)
"""
import json
import sys

from tests.sofa.off_scenarios import all_scenarios

with open(sys.argv[1], "w") as fh:
    json.dump(all_scenarios(), fh, indent=1, sort_keys=True)
    fh.write("\n")
