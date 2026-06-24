from pathlib import Path
from typing import Any, Dict
from .contracts import ProviderCaptureEnvelope
from .sanitizer import write_json

def write_provider_cache(
    output_dir: Path,
    envelope: ProviderCaptureEnvelope
) -> Path:
    """
    Write sanitized provider envelope to its designated cache directory.
    All cache files are kept strictly under reports/football_data_foundation/worldcup_20260624_live_shadow.
    
    This function performs safety checks:
    - Asserts that output_dir is an instance of Path.
    - Validates that envelope properties are non-empty.
    - Prevents cache writing if security boundaries are breached.
    """
    assert isinstance(output_dir, Path), "output_dir must be a Path object"
    assert envelope is not None, "envelope must not be None"
    assert envelope.provider, "envelope provider key must not be empty"
    assert envelope.fixture_slug, "envelope fixture slug must not be empty"
    
    provider_key = envelope.provider
    slug = envelope.fixture_slug
    
    # Determine cache file path
    # Put discovery endpoints in separate files, detail endpoints in <slug>.json
    if "discovery" in envelope.request_purpose:
        filename = f"{slug}_discovery.json"
    else:
        filename = f"{slug}.json"
        
    cache_path = output_dir / "cache" / provider_key / filename
    
    # Secure absolute path validation before any writing occurs
    abs_str = str(cache_path.resolve())
    if "reports/football_data_foundation/worldcup_20260624_live_shadow" not in abs_str:
        raise ValueError(f"Security breach: attempted write outside permitted directory: {abs_str}")
        
    write_json(cache_path, envelope.to_dict())
    return cache_path

