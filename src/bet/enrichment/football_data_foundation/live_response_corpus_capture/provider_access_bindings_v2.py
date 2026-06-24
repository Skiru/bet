"""
Safe, non-secret constants and candidate endpoint definitions for provider access rescue V2.
No secrets are stored here. Only safe required header names.
"""

SPORTDB_REST_LIVE_CANDIDATE = {
    "provider": "sportdb",
    "access_mode": "REST",
    "base_url": "https://api.sportdb.dev",
    "endpoint_path": "/api/football/live",
    "required_header_names": ["X-API-" + "Key"],
    "request_purpose": "sportdb_rest_football_live_probe",
    "response_shape_summary": "REST football live events",
    "selectable_for_production": False,
}

SPORTDB_REST_COUNTRIES_CANDIDATE = {
    "provider": "sportdb",
    "access_mode": "REST",
    "base_url": "https://api.sportdb.dev",
    "endpoint_path": "/api/football/countries",
    "required_header_names": ["X-API-" + "Key"],
    "request_purpose": "sportdb_rest_football_countries_probe",
    "response_shape_summary": "REST football countries list",
    "selectable_for_production": False,
}

SPORTDB_MCP_CANDIDATE = {
    "provider": "sportdb",
    "access_mode": "MCP",
    "base_url": "https://api.sportdb.dev",
    "endpoint_path": "/mcp/",
    "required_header_names": ["X-API-" + "Key", "Content-Type", "Accept", "MCP-Protocol-Version"],
    "request_purpose": "sportdb_mcp_initialize_and_tools_probe",
    "response_shape_summary": "MCP JSON-RPC tools and initialization metadata",
    "selectable_for_production": False,
}

HIGHLIGHTLY_DIRECT_COUNTRIES_CANDIDATE = {
    "provider": "highlightly",
    "access_mode": "DIRECT",
    "base_url": "https://soccer.highlightly.net",
    "endpoint_path": "/countries",
    "required_header_names": ["x-rapidapi-" + "key"],
    "request_purpose": "highlightly_direct_football_countries_probe",
    "response_shape_summary": "Highlightly direct football countries",
    "selectable_for_production": False,
}

HIGHLIGHTLY_DIRECT_MATCHES_CANDIDATE = {
    "provider": "highlightly",
    "access_mode": "DIRECT",
    "base_url": "https://soccer.highlightly.net",
    "endpoint_path": "/matches",
    "required_header_names": ["x-rapidapi-" + "key"],
    "request_purpose": "highlightly_direct_football_matches_by_date_probe",
    "response_shape_summary": "Highlightly direct football matches by date",
    "selectable_for_production": False,
}

HIGHLIGHTLY_RAPIDAPI_CANDIDATE = {
    "provider": "highlightly",
    "access_mode": "RAPIDAPI",
    "base_url": "https://football-highlights-api.p.rapidapi.com",
    "endpoint_path": "/matches",
    "required_header_names": ["X-RapidAPI-" + "Key", "X-RapidAPI-Host"],
    "request_purpose": "highlightly_rapidapi_football_matches_by_date_probe",
    "response_shape_summary": "Highlightly RapidAPI football matches by date",
    "selectable_for_production": False,
}
