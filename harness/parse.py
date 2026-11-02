import json
import logging


def parse_json_loose(text: str):
    raw = (text or "").strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 3:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
    return json.loads(raw)

VALID_RULES = {"R1", "R2", "R3", "R4", "R5"}
VALID_SEVERITIES = {"blocker", "major", "minor"}

SEVERITY_ALIASES = {
    "error": "blocker",
    "critical": "blocker",
    "fatal": "blocker",
    "high": "blocker",
    "warning": "major",
    "warn": "major",
    "medium": "major",
    "info": "minor",
    "note": "minor",
    "hint": "minor",
    "low": "minor",
}


def normalize_findings(raw: list) -> list[dict]:
    out: list[dict] = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        rule = str(f.get("rule", "R?"))
        sev = str(f.get("severity", "minor")).lower().strip()
        sev = SEVERITY_ALIASES.get(sev, sev)
        if sev not in VALID_SEVERITIES:
            logging.warning("unknown severity %r → defaulting to minor", sev)
            sev = "minor"
        if rule not in VALID_RULES:
            logging.warning("unknown rule id %r — keeping as-is", rule)
        out.append({
            "rule": rule,
            "severity": sev,
            "reason": str(f.get("reason", ""))[:500],
        })
    return out