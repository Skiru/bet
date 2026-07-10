import json
import sys
from pathlib import Path
from bet.pipeline.manifest import load_pipeline_manifest, validate_pipeline_manifest

def main():
    manifest = load_pipeline_manifest(Path("config/pipeline_manifest.json"))
    errors = validate_pipeline_manifest(manifest, Path.cwd())
    print(json.dumps({
      "pipeline_id": manifest.pipeline_id,
      "steps": [s.id for s in manifest.steps],
      "agents": {s.id: s.agent for s in manifest.steps},
      "errors": errors,
    }, indent=2, default=str))
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
