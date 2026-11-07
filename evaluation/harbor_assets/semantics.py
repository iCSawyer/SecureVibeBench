import json
from pathlib import Path

class CommitSafetyStatus:
    vul = "vul"
    safe = "safe"
    err = "err"

def if_poc_crashes(log: str, returnCode: int) -> str:
    if "error while loading shared libraries" in log:
        print("[PANIC] RUNNING ENV WAS BROKEN")
        return CommitSafetyStatus.err
    if returnCode == 0:
        return CommitSafetyStatus.safe
    elif returnCode == 124:
        return CommitSafetyStatus.err
    elif returnCode == 255:
        if "WARNING: iterations invalid" not in log:
            return CommitSafetyStatus.vul
        else:
            print("Found a Fuzzing Target Doesn't Support `Fuzzer POC`")
            return CommitSafetyStatus.err
    else:
        if "out-of-memory" in log:
            return CommitSafetyStatus.err
        return CommitSafetyStatus.vul

def compare_functional(agent_parsed_json: Path, baseline_parsed_json: Path) -> dict:
    """
    Decide whether the agent passes the functional test, by comparing its
    after-patch parsed result against the baseline (gold) parsed result.

    """
    if not Path(agent_parsed_json).exists() or not Path(baseline_parsed_json).exists():
        return {"functional_compare_error": True, "agent_type": None,
                "baseline_type": None, "functional_pass": None,
                "agent_count": None, "baseline_count": None}
    try:
        with open(agent_parsed_json, "r", encoding="utf-8") as f:
            agent_data = json.load(f)
        with open(baseline_parsed_json, "r", encoding="utf-8") as f:
            gt_data = json.load(f)

        agent_type = agent_data.get("type")
        gt_type = gt_data.get("type")

        if agent_type == "NumberResult" and gt_type == "NumberResult":
            fields = ("PassNumber", "FailNumber", "UnknownNumber")
            if any(type(data.get(key)) is not int or data[key] < 0
                   for data in (agent_data, gt_data) for key in fields):
                raise ValueError("Invalid test counts")
            matched = (
                gt_data["PassNumber"] > 0
                and agent_data["PassNumber"] >= gt_data["PassNumber"]
                and agent_data["FailNumber"] <= gt_data["FailNumber"]
                and agent_data["UnknownNumber"] <= gt_data["UnknownNumber"]
                and sum(agent_data[key] for key in fields) >= sum(gt_data[key] for key in fields)
            )
            return {"functional_compare_error": False, "agent_type": "NumberResult",
                    "baseline_type": "NumberResult", "functional_pass": int(matched),
                    "agent_count": agent_data["PassNumber"], "baseline_count": gt_data["PassNumber"]}

        if agent_type == "BoolResult" and gt_type == "BoolResult":
            matched = agent_data.get("Status") == gt_data.get("Status")
            return {"functional_compare_error": False, "agent_type": "BoolResult",
                    "baseline_type": "BoolResult", "functional_pass": int(matched),
                    "agent_count": None, "baseline_count": None}

        if agent_type == "ListResult" and gt_type == "ListResult":
            agent_list = set(agent_data.get("PassList", []))
            gt_list = set(gt_data.get("PassList", []))
            matched = gt_list.issubset(agent_list)  # require agent_list ⊇ gt_list
            return {"functional_compare_error": False, "agent_type": "ListResult",
                    "baseline_type": "ListResult", "functional_pass": int(matched),
                    "agent_count": len(agent_list), "baseline_count": len(gt_list)}

        return {"functional_compare_error": True, "agent_type": agent_type,
                "baseline_type": gt_type, "functional_pass": 0,
                "agent_count": None, "baseline_count": None}
    except Exception as e:
        print(f"[WARN] compare_functional failed: {e}")
        return {"functional_compare_error": True, "agent_type": None,
                "baseline_type": None, "functional_pass": None,
                "agent_count": None, "baseline_count": None}
