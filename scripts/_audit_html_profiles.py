#!/usr/bin/env python3
"""Audit HTML domains vs extraction profiles."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from html_deep_parser import PROFILES

data_dir = os.path.join(os.path.dirname(__file__), '..', 'betting', 'data')
all_domains = {}
for entry in os.listdir(data_dir):
    path = os.path.join(data_dir, entry)
    if os.path.isdir(path):
        htmls = [f for f in os.listdir(path) if f.endswith('.html')]
        if htmls:
            all_domains[entry] = len(htmls)

profiled = set(PROFILES.keys())
print('=== DOMAINS WITH HTML BUT NO PROFILE ===')
for domain in sorted(all_domains, key=lambda x: -all_domains[x]):
    if domain not in profiled:
        print(f'  {domain:30s} {all_domains[domain]:4d} HTML files')

print('\n=== PROFILES WITH 0 EXTRACTIONS (BROKEN) ===')
broken = ['soccerstats.com', 'betexplorer.com', 'covers.com', 'hltv.org', 'betclic.pl', 'tennisexplorer.com']
for d in broken:
    if d in profiled:
        print(f'  {d:30s} {all_domains.get(d, 0):4d} HTML files')
