import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.parse import parse_json_loose
s = '```json\n{"chosen": 2, "rationale": "..."}\n```'
p = parse_json_loose(s)
print(p)
print(p["chosen"])
print(p["rationale"])
