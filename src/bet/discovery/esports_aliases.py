"""Canonical esports team aliases for cross-source name resolution.

Used by dedup engine and stats routing to match names across
odds-api.io, HLTV, VLR, OpenDota, GosuGamers, etc.

Esports teams use acronyms, full names, and variant spellings across sources.
Standard fuzzy matching (85% threshold) fails for short names (NaVi vs Natus Vincere).
This registry provides deterministic alias resolution.
"""

# canonical_name (lowercased) → set of known aliases (all lowercase)
ESPORTS_ALIASES: dict[str, set[str]] = {
    # --- CS2 Teams ---
    "natus vincere": {"navi", "na'vi", "na`vi", "natus vincere cs2", "navi cs2"},
    "faze clan": {"faze", "faze cs2"},
    "g2 esports": {"g2", "g2.ig", "g2 cs2"},
    "team liquid": {"liquid", "tl", "team liquid cs2"},
    "cloud9": {"c9", "cloud 9", "cloud9 cs2"},
    "team vitality": {"vitality", "vit"},
    "virtus.pro": {"vp", "virtus pro", "virtuspro"},
    "ninjas in pyjamas": {"nip", "ninjas in pajamas"},
    "mouz": {"mousesports", "mouz nxt"},
    "fnatic": {"fnc"},
    "heroic": set(),
    "astralis": set(),
    "complexity": {"col", "complexity gaming"},
    "eternal fire": {"efs", "eternalfire"},
    "big": {"big clan"},
    "ence": {"ence esports"},
    "monte": {"monte esports"},
    "saw": {"saw esports"},
    "3dmax": set(),
    "the mongolz": {"mongolz"},
    "pain gaming": {"pain", "paing"},
    "imperial esports": {"imperial", "imp"},
    "mibr": {"made in brazil"},
    # --- Dota 2 Teams ---
    "team spirit": {"spirit", "ts", "team spirit dota"},
    "team falcons": {"falcons", "tf"},
    "gaimin gladiators": {"gg", "gaimin"},
    "tundra esports": {"tundra"},
    "og": {"og esports", "og dota"},
    "beastcoast": {"bc"},
    "evil geniuses": {"eg"},
    "9pandas": {"9p", "9 pandas"},
    "aurora gaming": {"aurora"},
    "bb team": {"betboom team", "betboom"},
    "xtreme gaming": {"xtreme", "xg"},
    "nigma galaxy": {"nigma"},
    "talon esports": {"talon"},
    "blacklist international": {"blacklist", "blck"},
    "azure ray": set(),
    "nouns": {"nouns esports"},
    # --- Valorant Teams ---
    "sentinels": {"sen"},
    "loud": set(),
    "drx": {"drx valorant"},
    "paper rex": {"prx"},
    "fnatic": {"fnc"},
    "gen.g esports": {"gen.g", "geng"},
    "t1": {"t1 valorant"},
    "nrg esports": {"nrg"},
    "100 thieves": {"100t"},
    "evil geniuses": {"eg"},
    "team heretics": {"heretics", "ths"},
    "edward gaming": {"edg", "edward"},
    "bilibili gaming": {"blg"},
    "trace esports": {"trace"},
    "detonation focusme": {"dfm", "detonation"},
    "global esports": {"global", "ge"},
    "leviatán": {"lev", "leviatan"},
    "kru esports": {"kru"},
    "furia": {"furia esports"},
    "mibr": {"made in brazil"},
    "tyloo": {"tyloo valorant"},
    # --- Cross-game orgs ---
    "team liquid": {"liquid", "tl"},
    "fnatic": {"fnc"},
    "cloud9": {"c9", "cloud 9"},
    "evil geniuses": {"eg"},
    "nrg esports": {"nrg"},
    "g2 esports": {"g2"},
    "100 thieves": {"100t"},
    "t1": set(),
}


def resolve_alias(name: str) -> str:
    """Resolve an alias to its canonical name.

    Returns the canonical name if found in registry, otherwise the original (lowered+stripped).
    """
    lower = name.lower().strip()

    # Direct canonical match
    if lower in ESPORTS_ALIASES:
        return lower

    # Check all alias sets
    for canonical, aliases in ESPORTS_ALIASES.items():
        if lower in aliases:
            return canonical

    return lower
