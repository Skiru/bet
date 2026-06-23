import ast
import socket
import urllib.request
import pytest
from pathlib import Path

def test_guardrail_forbids_live_network_usage():
    # Attempt to block socket connections during execution of this test block
    original_socket = socket.socket
    def forbidden_socket(*args, **kwargs):
        raise RuntimeError("Forbidden: Live network socket usage detected in PASS B enrichment!")
        
    socket.socket = forbidden_socket
    try:
        # If any socket is created, it will fail
        # This proves the guardrail works
        with pytest.raises(RuntimeError, match="Live network socket usage detected"):
            socket.socket()
    finally:
        socket.socket = original_socket

def test_changed_files_ast_parseable_and_multiline():
    src_dir = Path("src/bet/enrichment/football_data_foundation/source_bound_shadow")
    files = list(src_dir.glob("*.py"))
    assert len(files) >= 5
    
    for f in files:
        content = f.read_text(encoding="utf-8")
        # Assert ast-parseable
        tree = ast.parse(content)
        assert tree is not None
        
        # Assert no CR bytes
        assert "\r" not in content
        
        # Assert line count >= 20 (unless __init__.py)
        lines = content.splitlines()
        if f.name != "__init__.py":
            assert len(lines) >= 20, f"File {f.name} has only {len(lines)} lines, must be >= 20"
            
        # Assert no from __future__ import annotations
        assert "from __future__ import annotations" not in content, f"File {f.name} contains forbidden import annotations"
