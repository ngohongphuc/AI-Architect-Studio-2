"""Nhận diện phương án, giả định và vấn đề cần sửa của hồ sơ sơ bộ."""


def requires_repair(issue: dict) -> bool:
    return issue.get("ma") != "THIEU_CAN_CU" and issue.get("phan_loai") not in (
        "tham_chieu", "thieu_nguon", "thieu_thong_tin",
    )


def option_stamp(program: dict) -> str:
    if "option_version" not in program:
        return ""
    return f"{program['phuong_an']}:v{program['option_version']}:{program['revision_id']}"


def option_label(program: dict) -> str:
    if option_stamp(program):
        return f"Phương án {program['phuong_an']} · v{program['option_version']}"
    return ""


def selected_assumptions(state: dict) -> list[str]:
    program = state.get("program") or {}
    option = next((opt for opt in state.get("options") or []
                   if opt["program"].get("revision_id") == program.get("revision_id")), {})
    brief = state.get("brief") or {}
    return list(dict.fromkeys([*brief.get("gia_dinh_bo_sung", []), *option.get("gia_dinh", [])]))
