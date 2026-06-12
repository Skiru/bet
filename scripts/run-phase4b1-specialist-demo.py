#!/usr/bin/env python3
"""
Phase 4B-1 Specialist Demonstration Harness

This script invokes each canonical betting specialist with synthetic fixtures,
captures structured output, and validates results against expected outcomes.

Constraints:
- Sequential execution only
- No concurrent local model requests
- Bounded timeouts
- No --auto or --dangerously-skip-permissions
- Evidence persistence to demo directory
"""

import json
import os
import subprocess
import sys
import time
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Configuration
DEMO_ROOT = Path(__file__).parent.parent / "reports" / "betting-demo"
MAX_TIMEOUT_SECONDS = 300  # 5 minutes per scenario
RAPID_MLX_PID_FILE = Path("/tmp/rapid-mlx.pid")


class ScenarioResult:
    """Result of a single specialist scenario."""
    
    def __init__(self, scenario_id: str, agent: str, fixture: str):
        self.scenario_id = scenario_id
        self.agent = agent
        self.fixture = fixture
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.exit_status: Optional[int] = None
        self.actual_status: Optional[str] = None
        self.actual_decision: Optional[str] = None
        self.expected_status: Optional[str] = None
        self.expected_decision: Optional[str] = None
        self.match: bool = False
        self.tool_calls: List[str] = []
        self.permission_events: List[Dict] = []
        self.question_events: List[Dict] = []
        self.raw_output: str = ""
        self.error: Optional[str] = None
        self.session_id: Optional[str] = None
        self.model_used: Optional[str] = None
        self.rapidmlx_pid_before: Optional[int] = None
        self.rapidmlx_pid_after: Optional[int] = None
        self.overlap_detected: bool = False
        self.stalled: bool = False
        self.unauthorized_executions: List[str] = []
        self.output_schema_valid: bool = False


def get_rapidmlx_pid() -> Optional[int]:
    """Get current Rapid-MLX PID."""
    try:
        if RAPID_MLX_PID_FILE.exists():
            return int(RAPID_MLX_PID_FILE.read_text().strip())
        # Try to find via pgrep
        result = subprocess.run(
            ["pgrep", "-f", "rapid-mlx serve"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().split()[0])
    except Exception:
        pass
    return None


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def parse_output_schema(output: str) -> Dict[str, Optional[str]]:
    """Parse the required output schema from agent response."""
    result = {
        "STATUS": None,
        "DECISION": None,
        "EVIDENCE": None,
        "CALCULATIONS": None,
        "UNCERTAINTY": None,
        "RISKS": None,
        "NEXT_ACTION": None
    }
    
    for key in result.keys():
        pattern = rf"^{key}:\s*(.+?)(?=\n[A-Z]+:|$)"
        match = re.search(pattern, output, re.MULTILINE | re.DOTALL)
        if match:
            result[key] = match.group(1).strip()
    
    return result


def validate_output_schema(parsed: Dict[str, Optional[str]]) -> bool:
    """Validate that all required sections are present."""
    required = ["STATUS", "DECISION", "EVIDENCE", "UNCERTAINTY", "RISKS", "NEXT_ACTION"]
    return all(parsed.get(k) is not None for k in required)


def validate_status(status: Optional[str]) -> bool:
    """Validate that status is one of the allowed values."""
    allowed = {"PASS", "FAIL", "BLOCKED", "NO_DATA"}
    return status in allowed if status else False


def extract_tool_calls(output: str) -> List[str]:
    """Extract tool call names from JSON output."""
    tools = []
    # Look for tool calls in JSON events
    tool_pattern = r'"tool"\s*:\s*"([^"]+)"'
    tools.extend(re.findall(tool_pattern, output))
    return list(set(tools))


def extract_session_id(output: str) -> Optional[str]:
    """Extract session ID from JSON output."""
    match = re.search(r'"sessionId"\s*:\s*"([^"]+)"', output)
    return match.group(1) if match else None


def extract_model(output: str) -> Optional[str]:
    """Extract model identifier from JSON output."""
    patterns = [
        r'"model"\s*:\s*"([^"]+)"',
        r'"actualModel"\s*:\s*"([^"]+)"',
        r'"resolvedModel"\s*:\s*"([^"]+)"'
    ]
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    return None


def run_scenario(
    scenario: Dict,
    fixture_path: Path,
    demo_dir: Path,
    previous_end_time: Optional[datetime]
) -> ScenarioResult:
    """Run a single specialist scenario."""
    
    result = ScenarioResult(
        scenario_id=scenario["scenario_id"],
        agent=scenario["agent"],
        fixture=scenario["fixture"]
    )
    
    result.expected_status = scenario["expected_status"]
    result.expected_decision = scenario["expected_decision"]
    
    # Check for overlap with previous scenario
    if previous_end_time:
        gap = (datetime.now(timezone.utc) - previous_end_time).total_seconds()
        if gap < 1.0:
            result.overlap_detected = True
    
    result.rapidmlx_pid_before = get_rapidmlx_pid()
    result.start_time = datetime.now(timezone.utc)
    
    # Build the kilo run command
    # Use JSON format for structured output
    # Message must come after all options
    cmd = [
        "kilo", "run",
        "--agent", scenario["agent"],
        "--format", "json",
        "--title", f"Phase4B1-{scenario['scenario_id']}",
        "--file", str(fixture_path),
        "--",
        "Process the synthetic fixture in the attached file. Return your analysis following the required output schema with STATUS, DECISION, EVIDENCE, CALCULATIONS, UNCERTAINTY, RISKS, and NEXT_ACTION sections."
    ]
    
    # Run the command with timeout
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MAX_TIMEOUT_SECONDS,
            cwd=Path(__file__).parent.parent
        )
        result.exit_status = proc.returncode
        result.raw_output = proc.stdout + "\n" + proc.stderr
        
    except subprocess.TimeoutExpired:
        result.stalled = True
        result.error = "TIMEOUT"
        result.exit_status = -1
        result.raw_output = ""
        
    except Exception as e:
        result.error = str(e)
        result.exit_status = -1
        result.raw_output = ""
    
    result.end_time = datetime.now(timezone.utc)
    result.rapidmlx_pid_after = get_rapidmlx_pid()
    
    # Parse the output
    if result.raw_output:
        parsed = parse_output_schema(result.raw_output)
        result.actual_status = parsed.get("STATUS")
        result.actual_decision = parsed.get("DECISION")
        result.output_schema_valid = validate_output_schema(parsed)
        result.tool_calls = extract_tool_calls(result.raw_output)
        result.session_id = extract_session_id(result.raw_output)
        result.model_used = extract_model(result.raw_output)
        
        # Check for unauthorized tool usage
        forbidden = set(scenario.get("forbidden_tools", []))
        for tool in result.tool_calls:
            if tool in forbidden:
                result.unauthorized_executions.append(tool)
        
        # Check for permission prompts
        if "permission" in result.raw_output.lower() and "prompt" in result.raw_output.lower():
            result.permission_events.append({"type": "permission_prompt_detected"})
        
        # Check for question events
        if '"question"' in result.raw_output.lower():
            result.question_events.append({"type": "question_call_detected"})
    
    # Determine match
    if result.actual_status and result.actual_decision:
        result.match = (
            result.actual_status == result.expected_status and
            result.actual_decision == result.expected_decision
        )
    
    return result


def main():
    """Main demonstration harness."""
    
    # Find the demo directory
    demo_dirs = sorted(DEMO_ROOT.glob("phase4b1-*"))
    if not demo_dirs:
        print("ERROR: No demo directory found", file=sys.stderr)
        sys.exit(1)
    
    demo_dir = demo_dirs[-1]
    print(f"Demo directory: {demo_dir}")
    
    # Load expected outcomes
    expected_path = demo_dir / "EXPECTED_OUTCOMES.json"
    if not expected_path.exists():
        print(f"ERROR: Expected outcomes not found: {expected_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(expected_path) as f:
        expected = json.load(f)
    
    scenarios = expected["scenarios"]
    print(f"Scenarios to run: {len(scenarios)}")
    
    # Results storage
    results: List[ScenarioResult] = []
    previous_end_time: Optional[datetime] = None
    
    # Run each scenario sequentially
    for i, scenario in enumerate(scenarios):
        print(f"\n{'='*60}")
        print(f"Scenario {i+1}/{len(scenarios)}: {scenario['scenario_id']}")
        print(f"Agent: {scenario['agent']}")
        print(f"Expected: {scenario['expected_status']} / {scenario['expected_decision']}")
        print(f"{'='*60}")
        
        fixture_path = demo_dir / "fixtures" / scenario["fixture"]
        if not fixture_path.exists():
            print(f"ERROR: Fixture not found: {fixture_path}", file=sys.stderr)
            continue
        
        result = run_scenario(scenario, fixture_path, demo_dir, previous_end_time)
        results.append(result)
        previous_end_time = result.end_time
        
        # Print result
        print(f"\nActual: {result.actual_status} / {result.actual_decision}")
        print(f"Match: {result.match}")
        print(f"Schema valid: {result.output_schema_valid}")
        print(f"Tools called: {result.tool_calls}")
        print(f"Unauthorized: {result.unauthorized_executions}")
        print(f"Session ID: {result.session_id}")
        print(f"Model: {result.model_used}")
        print(f"Duration: {(result.end_time - result.start_time).total_seconds():.1f}s" if result.end_time and result.start_time else "N/A")
        
        if result.error:
            print(f"Error: {result.error}")
        
        # Save raw output
        run_dir = demo_dir / "agent-runs" / scenario["scenario_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = run_dir / "output.txt"
        with open(output_file, "w") as f:
            f.write(result.raw_output)
        
        # Small delay between scenarios
        time.sleep(2)
    
    # Generate results summary
    results_data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "results": []
    }
    
    for r in results:
        results_data["results"].append({
            "scenario_id": r.scenario_id,
            "agent": r.agent,
            "fixture": r.fixture,
            "expected_status": r.expected_status,
            "expected_decision": r.expected_decision,
            "actual_status": r.actual_status,
            "actual_decision": r.actual_decision,
            "match": r.match,
            "exit_status": r.exit_status,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "tool_calls": r.tool_calls,
            "unauthorized_executions": r.unauthorized_executions,
            "output_schema_valid": r.output_schema_valid,
            "session_id": r.session_id,
            "model_used": r.model_used,
            "rapidmlx_pid_before": r.rapidmlx_pid_before,
            "rapidmlx_pid_after": r.rapidmlx_pid_after,
            "overlap_detected": r.overlap_detected,
            "stalled": r.stalled,
            "error": r.error
        })
    
    results_file = demo_dir / "results.json"
    with open(results_file, "w") as f:
        json.dump(results_data, f, indent=2)
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    matches = sum(1 for r in results if r.match)
    schema_valid = sum(1 for r in results if r.output_schema_valid)
    unauthorized = sum(1 for r in results if r.unauthorized_executions)
    stalled = sum(1 for r in results if r.stalled)
    overlaps = sum(1 for r in results if r.overlap_detected)
    
    print(f"Total scenarios: {len(results)}")
    print(f"Expected outcomes matched: {matches}/{len(results)}")
    print(f"Output schema valid: {schema_valid}/{len(results)}")
    print(f"Unauthorized executions: {unauthorized}")
    print(f"Stalled scenarios: {stalled}")
    print(f"Overlap detected: {overlaps}")
    
    # Determine overall status
    all_match = matches == len(results)
    all_schema = schema_valid == len(results)
    no_unauthorized = unauthorized == 0
    no_stalled = stalled == 0
    no_overlap = overlaps == 0
    
    if all_match and all_schema and no_unauthorized and no_stalled and no_overlap:
        print("\nVERDICT: SPECIALIST_DEMO_PASS")
        sys.exit(0)
    else:
        print("\nVERDICT: SPECIALIST_DEMO_FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
