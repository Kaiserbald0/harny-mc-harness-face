from harness.parse import parse_json_loose
s = '```json\n{"chosen": 2, "rationale": "..."}\n```'
p = parse_json_loose(s)
print(p)
print(p["chosen"])
print(p["rationale"])
