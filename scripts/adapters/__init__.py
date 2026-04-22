"""Adapters package for scan_events.py

This module exposes a domain -> parser mapping. Each adapter must provide
`parse(html: str, url: str) -> List[Dict]`.
"""
from .raw_adapter import parse as raw_parse

# Domain-specific adapters (optional). If an adapter for a domain is not
# present, `raw_parse` will be used as a fallback.
ADAPTERS = {
	"forebet.com": raw_parse,
	"protipster.com": raw_parse,
	"flashscore.com": __import__(".flashscore_adapter", globals(), locals(), ["parse"]).parse,
	"sofascore.com": __import__(".sofascore_adapter", globals(), locals(), ["parse"]).parse,
	"oddsportal.com": __import__(".oddsportal_adapter", globals(), locals(), ["parse"]).parse,
	"betclic.pl": __import__(".betclic_adapter", globals(), locals(), ["parse"]).parse,
	"betclic.com": __import__(".betclic_adapter", globals(), locals(), ["parse"]).parse,
}


def get_adapter(domain: str):
	return ADAPTERS.get(domain, raw_parse)


