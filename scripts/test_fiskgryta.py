"""Offline validation of a Cookidoo Uploader recipe. Never authenticates or uploads."""
import importlib.util
import json
from pathlib import Path

from cookidoo_uploader.schema import build_payload, validate_payload

recipe_path = Path("recipes/fiskgryta_tm6.py")
spec = importlib.util.spec_from_file_location("fiskgryta_tm6", recipe_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
payload = build_payload(module.RECIPE, tool="TM6")
validate_payload(payload)
assert payload["tool"] == ["TM6"]
assert payload["yield"]["value"] == 4
assert len(payload["ingredients"]) == 14
assert len(payload["instructions"]) == 7
assert sum(1 for s in payload["instructions"] for a in s.get("annotations", []) if a["type"] == "TTS") == 3
assert all(a.get("data", {}).get("temperature", {}).get("value") != "Varoma" for s in payload["instructions"] for a in s.get("annotations", []))
output = Path("out/fiskgryta_tm6_cookidoo_dry_run.json")
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("OFFLINE DRY RUN OK")
print(f"Recipe: {payload['name']}")
print(f"Ingredients: {len(payload['ingredients'])}")
print(f"Steps: {len(payload['instructions'])}")
print("Cookidoo upload: NOT ATTEMPTED")
print(f"Output: {output}")
