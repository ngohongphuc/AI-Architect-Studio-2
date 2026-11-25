"""Chuyển các mốc SQLite thành khoảng xử lý, khoảng duyệt và dấu sự kiện."""
from datetime import datetime, timezone

from config import AGENT_LABELS, AGENT_ORDER

MARK_LABELS = {
    "queued": "Chờ bắt đầu", "canceled": "Hủy trước khi bắt đầu",
    "handoff": "Bàn giao", "repair": "Yêu cầu sửa", "retry": "Chạy lại", "approval": "Mời duyệt",
}


def timestamp(value: str | None) -> int | None:
    if not value:
        return None
    try:
        instant = datetime.fromisoformat(value)
        return round(instant.timestamp() * 1000) if instant.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def build_timeline(attempts: list[dict], events: list[dict], *, run_status: str, targets: dict,
                   agent: str | None = None) -> dict:
    """Chỉ kéo dài đầu mút chưa đóng của lần đang thực hiện hoặc đang chờ duyệt."""
    # Agent tùy biến (mã custom_…) có hàng riêng, đặt sau 9 agent lõi theo thứ tự xuất hiện trong lượt.
    custom = {item["agent_id"]: item.get("name") or item["agent_id"] for item in attempts
              if str(item.get("agent_id", "")).startswith("custom_")}
    titles = {**{key: AGENT_LABELS[key] for key in AGENT_ORDER}, **custom}
    names = [agent] if agent else [*AGENT_ORDER, *custom]
    rows = [{"id": key, "name": titles.get(key, key)} for key in names]
    plotted = []
    markers = []
    unfinished = set()
    missing_events = 0
    by_attempt = {row["attempt_id"]: row for row in attempts}

    def mark(ident, kind, at, owner, *, detail="", attempt_id=None):
        if at is not None:
            markers.append({"id": ident, "kind": kind, "label": MARK_LABELS[kind], "at": at,
                            "agent": owner, "detail": detail, "attempt_id": attempt_id})

    for item in attempts:
        ident, owner, status = item["attempt_id"], item["agent_id"], item["status"]
        if owner not in titles:
            continue
        assigned, start, end, request, decision = (
            timestamp(item[key]) for key in
            ("assigned_at", "started_at", "finished_at", "approval_requested_at", "decision_at")
        )
        active = status == "running" and run_status == "running"
        pending = status == "awaiting_approval" and run_status in ("running", "awaiting_approval", "needs_input", "paused")
        span = approval = None
        kind = None
        if start is not None and ((end is not None and end >= start) or (end is None and active)):
            span = [start, end]
        elif start is None and status in ("queued", "canceled") and assigned is not None:
            kind = status
        else:
            unfinished.add(ident)

        if request is not None:
            if (decision is not None and decision >= request) or (decision is None and pending):
                approval = [request, decision]
            else:
                unfinished.add(ident)
            mark(f"approval:{ident}", "approval", request, owner, attempt_id=ident, detail=item["name"])
        elif status == "awaiting_approval" or decision is not None:
            unfinished.add(ident)

        if kind:
            mark(f"{kind}:{ident}", kind, assigned, owner, attempt_id=ident, detail=item["name"])
        if item.get("retry_reason"):
            if assigned is None:
                unfinished.add(ident)
            mark(f"retry:{ident}", "retry", assigned, owner, attempt_id=ident, detail=item["retry_reason"])
        if item.get("acceptance") == "changes_requested":
            mark(f"repair:{ident}", "repair", decision, owner, attempt_id=ident, detail=item["name"])
        if span is not None or approval is not None:
            tone = {"error": "danger", "canceled": "neutral", "running": "info"}.get(status, "success")
            if approval is not None and status == "canceled":
                tone = "success"
            plotted.append({"id": ident, "agent": owner, "name": item["name"], "number": item["attempt_no"],
                            "status": status, "tone": tone, "processing": span, "approval": approval})

    for event in events:
        if event["status"] != "done" or not event.get("to_agent"):
            continue
        source = event["agent"]
        dest = targets.get(event["to_agent"], event["to_agent"])
        owner = dest if source == "user" else source
        if owner not in titles or (dest not in AGENT_LABELS and dest not in titles):
            continue
        at = timestamp(event.get("occurred_at"))
        if at is None:
            missing_events += int(owner in names)
            continue
        ident = event.get("attempt_id")
        item = by_attempt.get(ident)
        category = "repair" if item and item.get("repair_iteration") is not None and event.get("feedback") else "handoff"
        route = f"{titles.get(source, AGENT_LABELS.get(source, source))} → {titles.get(dest, AGENT_LABELS.get(dest, dest))}"
        detail = f"{route} · {event['summary']}" if event.get("summary") else route
        mark(f"event:{event['id']}", category, at, owner, attempt_id=ident if item else None, detail=detail)

    spans = [span for item in plotted for span in (item["processing"], item["approval"]) if span]
    instants = [item["at"] for item in markers] + [at for span in spans for at in span if at is not None]
    extent = ({"start": min(instants), "end": max(instants), "live": any(span[1] is None for span in spans)}
              if instants else None)
    return {"rows": rows, "extent": extent, "attempts": [item for item in plotted if item["agent"] in names],
            "markers": [item for item in markers if item["agent"] in names],
            "missing_attempts": sum(by_attempt[ident]["agent_id"] in names for ident in unfinished),
            "missing_events": missing_events, "server_now": round(datetime.now(timezone.utc).timestamp() * 1000)}
