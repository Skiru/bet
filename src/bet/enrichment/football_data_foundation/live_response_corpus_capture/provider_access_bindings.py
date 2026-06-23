"""
Safe, non-secret constants and candidate endpoint definitions for provider access rescue.
No secrets are stored here. Only safe required header names.
"""

SPORTDB_REST_CANDIDATE = {
    "provider": "sportdb",
    "access_mode": "REST",
    "base_url": "https://api.sportdb.dev",
    "endpoint_path": "/api/football/live",
    "required_header_names": ["X-API-Key"],
    "request_purpose": "sportdb_rest_live_probe",
    "response_shape_summary": "REST football live events",
    "selectable_for_production": False,
}

SPORTDB_MCP_CANDIDATE = {
    "provider": "sportdb",
    "access_mode": "MCP",
    "base_url": "https://api.sportdb.dev",
    "endpoint_path": "/mcp/",
    "required_header_names": ["X-API-Key", "Content-Type", "Accept", "MCP-Protocol-Version"],
    "request_purpose": "sportdb_mcp_initialize_and_tools_probe",
    "response_shape_summary": "MCP JSON-RPC tools and initialization metadata",
    "selectable_for_production": False,
}

HIGHLIGHTLY_DIRECT_CANDIDATE = {
    "provider": "highlightly",
    "access_mode": "DIRECT",
    "base_url": "https://sports.highlightly.net",
    "endpoint_path": "/football/matches",
    "required_header_names": ["x-rapidapi-key"],
    "request_purpose": "highlightly_direct_matches_by_date_probe",
    "response_shape_summary": "Highlightly direct matches metadata",
    "selectable_for_production": False,
}

HIGHLIGHTLY_RAPIDAPI_CANDIDATE = {
    "provider": "highlightly",
    "access_mode": "RAPIDAPI",
    "base_url": "https://sport-highlights-api.p.rapidapi.com",
    "endpoint_path": "/football/matches",
    "required_header_names": ["x-rapidapi-key", "x-rapidapi-host"],
    "request_purpose": "highlightly_rapidapi_matches_by_date_probe",
    "response_shape_summary": "Highlightly RapidAPI matches metadata",
    "selectable_for_production": False,
}
