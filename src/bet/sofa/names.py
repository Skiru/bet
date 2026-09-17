import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict

DIACRITICS_FOLD = {
    'ø': 'o', 'ł': 'l', 'đ': 'd', 'ı': 'i',
    'æ': 'ae', 'ß': 'ss', 'ð': 'd', 'þ': 'th'
}

_ALIASES_CACHE: Dict[str, str] = {}
_ALIASES_LOADED = False

def get_aliases() -> Dict[str, str]:
    global _ALIASES_LOADED
    if not _ALIASES_LOADED:
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "sofa_name_aliases.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                _ALIASES_CACHE.update(json.load(f))
        _ALIASES_LOADED = True
    return _ALIASES_CACHE

def normalize_name(name: str) -> str:
    name = name.strip()
    
    # 1. Custom diacritics fold before NFD
    for char, replacement in DIACRITICS_FOLD.items():
        name = name.replace(char, replacement)
        name = name.replace(char.upper(), replacement.upper())
        
    # 2. NFD normalization and remove non-ASCII
    name = unicodedata.normalize('NFD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    
    name = name.lower()
    
    # 3. Polish team/country names & specific suffixes
    # " (k)" -> " w"
    # " u20" -> " u20" etc (already standard, but ensure we don't mess it up)
    name = name.replace(" (k)", " w")
    
    aliases = get_aliases()
    
    # Extract prefixes to map if they exist in aliases
    words = name.split()
    if words:
        # Check first word
        if words[0] in aliases:
            words[0] = aliases[words[0]]
        # Check first two words (e.g., "stany zjednoczone")
        elif len(words) >= 2:
            two_words = f"{words[0]} {words[1]}"
            if two_words in aliases:
                words[0] = aliases[two_words]
                del words[1]
                
        name = " ".join(words)
            
    # 4. Reserves marker
    # (R) <-> II / B / U21 -> (R)
    # We should normalize all to "(r)"
    name = re.sub(r'\bii\b', '(r)', name)
    name = re.sub(r'\bb\b', '(r)', name)
    name = re.sub(r'\bu21\b', '(r)', name)
    
    # Clean up parentheses around markers just in case
    name = re.sub(r'\(\(r\)\)', '(r)', name)
    name = re.sub(r'\s+\(r\)', ' (r)', name)
    name = re.sub(r'(\s*\(r\))+', ' (r)', name)
    
    return name.strip()
