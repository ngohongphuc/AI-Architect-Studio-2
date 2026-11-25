"""Dữ liệu mock tất định cho tab Hiệu suất và các bài kiểm tra công thức."""
from monitoring.performance import Task

RUNS = {"mock-studio-a": "Mock · Nhà phố A", "mock-studio-b": "Mock · Nhà phố B", "mock-studio-c": "Mock · Nhà phố C"}


def sample() -> list[Task]:
    def attempt(run, stage, number, day, processing, wait, *, accepted=False, score=None, maximum=100,
                tokens=None, cost=None, fault=False, estimate=False, processed=True, model=None, pending=False):
        at = f"2025-01-{day:02d}T09:00:00+07:00"
        return {"attempt_id": f"{run}:{stage}:{number}", "attempt_no": number, "assigned_at": at, "started_at": at,
                "decision_at": at if accepted else None, "status": "completed" if processed else "error",
                "acceptance": "accepted" if accepted else "pending" if pending else None, "processed": processed,
                "approval_requested_at": at if pending else None, "finished_at": at if processed else None, "tokens": tokens,
                "cost_usd": cost, "cost_basis": ("estimated" if estimate else "reported") if cost is not None else None,
                "model": model, "processing_s": processing, "wait_s": wait, "earned": score,
                "applicable": maximum if score is not None else None, "score_status": "complete" if score is not None else None,
                "retry_category": ("agent_error" if fault else "infrastructure") if number > 1 else None,
                "agent_fault_confirmed": fault, "agent_fault_evidence": "Mock · Đã đối chiếu số phòng sai." if fault else "",
                "reviewer": "Người chấm mock", "reviewed_at": at, "output_version": f"A · v{number}"}

    def work(run, stage, name, *details):
        return Task(f"{run}:{stage}", run, stage, stage, name, details)

    a, b, c = RUNS
    return [
        work(a, "architect", "Thiết kế công năng",
             attempt(a, "architect", 1, 12, 10, 2, accepted=True, score=82, tokens=100, cost=.10, model="mock-1"),
             attempt(a, "architect", 2, 13, 18, 4, accepted=True, score=90, tokens=200, cost=.20, fault=True, model="mock-2")),
        work(b, "architect", "Thiết kế công năng",
             attempt(b, "architect", 1, 12, 8, 1, tokens=50, cost=.05, processed=False, model="mock-1"),
             attempt(b, "architect", 2, 14, 31, 5, accepted=True, score=70, maximum=70, tokens=250, cost=.25,
                     estimate=True, model="mock-1")),
        work(c, "architect", "Thiết kế công năng", attempt(c, "architect", 1, 14, 15, 3, score=88, pending=True)),
        work(a, "drafter", "Triển khai bản vẽ", attempt(a, "drafter", 1, 12, 7, 2)),
    ]
