"""Read named test outcomes without converting counts into invented cases."""

import re

STATUSES = frozenset({"PASS", "FAIL", "ERROR", "SKIP", "XFAIL", "XPASS", "NOT_RUN"})


def status_map(results):
    if not isinstance(results, dict):
        raise ValueError("Expected a map of test IDs to outcomes")
    normalized = {}
    for name, value in results.items():
        status = value.get("status") if isinstance(value, dict) else value
        if not isinstance(name, str) or not name.strip() or not isinstance(status, str) or status not in STATUSES:
            raise ValueError("Invalid named test outcome: " + str(name))
        normalized[name] = status
    return normalized


def from_named_result(result):
    """Adapt the existing list format; aggregate counts are insufficient evidence."""
    if result.get("type") != "ListResult":
        raise ValueError("F2P/P2P requires named results; counts and booleans are insufficient")
    outcomes = {}
    for field, status in (("PassList", "PASS"), ("FailList", "FAIL"), ("UnknownList", "NOT_RUN"), ("SkipList", "SKIP"), ("XFailList", "XFAIL"), ("XPassList", "XPASS")):
        values = result.get(field, [])
        if not isinstance(values, list) or any(not isinstance(name, str) for name in values):
            raise ValueError("Named test outcomes require lists of case IDs")
        for name in values:
            if name in outcomes:
                raise ValueError("Duplicate or contradictory test ID: " + name)
            outcomes[name] = status
    return status_map(outcomes)


def from_dejagnu(text, suite):
    """Read individual DejaGNU outcomes; reject ambiguous repeated test names."""
    outcomes, script = {}, ""
    statuses = {"PASS": "PASS", "FAIL": "FAIL", "XPASS": "XPASS", "XFAIL": "XFAIL",
                "UNRESOLVED": "ERROR", "UNTESTED": "NOT_RUN", "UNSUPPORTED": "SKIP"}
    for line in text.splitlines():
        running = re.match(r"Running (.+?\.exp)(?:\s+\.\.\.)?\s*$", line)
        if running:
            script = re.sub(r"^(?:\.\./)+", "", running.group(1))
        match = re.match(r"^(PASS|FAIL|XPASS|XFAIL|UNRESOLVED|UNTESTED|UNSUPPORTED):\s+(.+)$", line)
        if match:
            if not script:
                raise ValueError("DejaGNU result has no test-script context")
            name = "::".join((suite, script, match.group(2)))
            if name in outcomes:
                raise ValueError("Ambiguous DejaGNU test ID: " + name)
            outcomes[name] = statuses[match.group(1)]
    if not outcomes:
        raise ValueError("No individual DejaGNU outcomes found")
    return outcomes
