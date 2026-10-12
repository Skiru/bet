#!/usr/bin/env python3
"""Regenerate golden/offer_mappable_off.json from an ARCHIVE of the commit the
MAPPABLE_FAMILIES switch was added on top of (40b42923), not the working tree:

    d=$(mktemp -d) && git archive 40b42923 src scripts config tests | tar -x -C $d
    cp tests/sofa/offer_mappable_scenarios.py $d/tests/sofa/ && cp tests/sofa/golden/offer_mappable_items.json $d/tests/sofa/golden/
    (cd $d && PYTHONPATH=src:. <repo>/.venv/bin/python tests/sofa/golden/make_offer_mappable_golden.py <repo>/tests/sofa/golden/offer_mappable_off.json)
"""
import sys

from tests.sofa.offer_mappable_scenarios import dumps, offer_dump

with open(sys.argv[1], "w", encoding="utf-8") as fh:
    fh.write(dumps(offer_dump(None)))
    fh.write("\n")
