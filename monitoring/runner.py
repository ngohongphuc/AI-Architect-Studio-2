"""Điều khiển lượt thiết kế chạy nền cho giao diện Streamlit.

- Chạy `graph.stream(..., stream_mode="updates")` trong thread riêng.
- Tạm dừng: dừng sau khi agent hiện tại chạy xong; trạng thái nằm trong checkpointer (SQLite) để chạy tiếp.
- Dừng: hủy lượt thiết kế.
- Duyệt thủ công: graph dừng ở `interrupt`, tiếp tục bằng `Command(resume=...)`.
- Chạy lại agent: tái tạo đầu ra phụ thuộc và giữ nguyên số vòng sửa.
"""
from __future__ import annotations

import threading
import time
from contextlib import closing
from dataclasses import dataclass, field

from langgraph.types import Command

from agents.project_manager import save_snapshot
from config import AGENT_ORDER, MAX_ITERATIONS
from graph import (NODE_AGENT, STAGE_OUTPUTS, WORKFLOW_RECURSION_LIMIT, _run_summary, build_graph, initial_state, invalidate_from,
                   outcome_for, select_option, sqlite_checkpointer)
from monitoring import events, tasks
from monitoring.redaction import error_text, redact
from monitoring.tracker import estimate_cost_usd, tracker

_graph = None
_graph_lock = threading.Lock()


def get_graph():
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = build_graph(sqlite_checkpointer())
        return _graph


@dataclass
class Run:
    run_id: str
    request: str
    status: str = "idle"          # running | paused | awaiting_approval | done | stopped | error
    current_node: str = ""
    started: float = field(default_factory=time.time)
    elapsed: float = 0.0
    error: str = ""
    interrupt_payload: dict | None = None
    pause_requested: bool = False
    stop_requested: bool = False
    thread: threading.Thread | None = None
    _t_start: float = 0.0
    _dispatch_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def config(self) -> dict:
        return {"configurable": {"thread_id": self.run_id}, "recursion_limit": WORKFLOW_RECURSION_LIMIT}

    # ------------------------------------------------------------------
    def _loop(self, inp, config=None) -> None:
        cfg = config or self.config
        self.status = "running"
        t0 = self._t_start = time.time()
        try:
            g = get_graph()
            snap = g.get_state(cfg) if inp is None else None
            self.current_node = (snap.next[0] if snap and snap.next else "project_manager")
            if snap:
                tasks.queue_ready(snap.values, ((task.id, task.name) for task in snap.tasks if not task.interrupts))
            with closing(tasks.stream_tracked(g, inp, cfg)) as stream:
                for kind, update in stream:
                    if kind == "checkpoints":
                        self.current_node = update["next"][0] if update["next"] else ""
                        if self.stop_requested or self.pause_requested:
                            break
                    elif "__interrupt__" in update:
                        break
            snap = g.get_state(self.config)
            pending = [i for t in snap.tasks for i in (t.interrupts or [])]
            self.current_node = snap.next[0] if snap.next else ""
            self.pause_requested = False
            if self.stop_requested or snap.values.get("outcome") == "stopped":
                self.status = "stopped"
                tasks.cancel_open(self.run_id, "Lượt thiết kế đã dừng")
                events.update_run(self.run_id, "stopped")
            elif snap.next and pending:
                self.interrupt_payload = pending[0].value
                self.status = "needs_input" if self.interrupt_payload.get("clarification") else "awaiting_approval"
                events.update_run(self.run_id, self.status)
            elif snap.next:
                self.status = "paused"
                events.update_run(self.run_id, "paused")
            else:
                self.status = outcome_for(snap.values)
                self.current_node = ""
                save_snapshot(snap.values)
                events.update_run(self.run_id, self.status, _run_summary(snap.values))
        except Exception as e:  # noqa: BLE001
            self.status = "error"
            self.error = error_text(e)
            tasks.cancel_open(self.run_id, "Lượt thiết kế gặp lỗi")
            events.update_run(self.run_id, "error")
        finally:
            self.elapsed += time.time() - t0

    def _start(self, inp, config=None) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_requested = self.pause_requested = False
        self.interrupt_payload = None
        self.status = "running"          # đặt ngay để giao diện không thấy trạng thái cũ
        events.update_run(self.run_id, "running")
        self.thread = threading.Thread(target=self._loop, args=(inp, config), daemon=True)
        self.thread.start()

    # ------------------------------------------------------------------
    def pause(self):
        self.pause_requested = True

    def resume(self):
        with self._dispatch_lock:
            if self.status == "paused":
                self._start(None)

    def stop(self):
        with self._dispatch_lock:
            self.stop_requested = True
            if self.status in ("paused", "awaiting_approval", "needs_input"):
                self.status = "stopped"
                tasks.cancel_open(self.run_id, "Lượt thiết kế đã dừng")
                events.update_run(self.run_id, "stopped")

    def answer(self, action: str, feedback: str = "", **data):
        """Trả lời điểm duyệt thủ công: approve | revise | edit (rows, settings) | stop."""
        with self._dispatch_lock:
            if self.status in ("awaiting_approval", "needs_input") and self.interrupt_payload:
                self._start(Command(resume=redact({"action": action, "feedback": feedback, **data})))

    def can_rerun(self, agent: str, state: dict) -> bool:
        needs = {
            "concept_architect": ("brief",), "architect": ("brief",),
            "drafter": ("brief", "program"), "reviewer": ("layout", "area_table"),
            "fengshui_advisor": ("layout",), "cost_estimator": ("layout", "area_table"),
            "final_reviewer": ("draft_files",),
        }
        return (self.status != "running"
                and any(h["agent"] == agent for h in state.get("history", []))
                and all(state.get(key) is not None for key in needs.get(agent, ())))

    def rerun_agent(self, agent: str, *, expected_revision: str | None = None) -> bool:
        """Chạy lại một agent và tái tạo các kết quả phụ thuộc từ trạng thái mới nhất."""
        with self._dispatch_lock:
            if self.thread and self.thread.is_alive():
                return False
            g = get_graph()
            current = g.get_state(self.config)
            if agent not in STAGE_OUTPUTS or not self.can_rerun(agent, current.values):
                return False
            if expected_revision is not None and current.values.get("revision_id") != expected_revision:
                return False
            updates = {**invalidate_from(agent), "route": agent, "feedback": [],
                       "task_retry": {"reason": "Người dùng yêu cầu chạy lại agent", "category": "unknown"}}
            if agent in ("project_manager", "requirements_analyst", "concept_architect", "architect"):
                updates["program"] = None
            cfg = g.update_state(current.config, updates, as_node="dispatch")
            tasks.cancel_open(self.run_id, "Được thay bằng lượt giao chạy lại")
            self._start(None, cfg)
            return True

    def choose_option(self, option_id: str, *, expected_revision: str | None = None) -> bool:
        with self._dispatch_lock:
            if self.status not in ("done", "not_passed") or (self.thread and self.thread.is_alive()):
                return False
            g = get_graph()
            current = g.get_state(self.config)
            previous = (current.values.get("program") or {}).get("phuong_an")
            if not current.values or current.next or option_id == previous:
                return False
            updates = select_option(current.values, option_id)
            if updates is None or (expected_revision is not None and updates["revision_id"] != expected_revision):
                return False
            cfg = g.update_state(current.config, updates, as_node="dispatch")
            events.emit(self.run_id, updates["events"][0])
            self._start(None, cfg)
            return True

    # ------------------------------------------------------------------
    def state(self) -> dict:
        try:
            st = get_graph().get_state(self.config).values or {}
        except Exception:  # noqa: BLE001
            st = {}
        if st:
            return st
        # Lượt chạy không có checkpoint (CLI cũ, evaluate, test) -> đọc state.json trong thư mục kết quả
        snap = load_snapshot(self.run_id)
        return snap or st

    def tokens(self) -> int:
        live = tracker.tokens(self.run_id)
        return live or sum(e["tokens"] or 0 for e in events.get_events(self.run_id) if e["status"] == "done")

    def cost_usd(self) -> float:
        return tracker.usd(self.run_id) or estimate_cost_usd(self.tokens())

    def step(self) -> tuple[int, str]:
        agent = NODE_AGENT.get(self.current_node, "")
        if self.status in ("done", "not_passed"):
            return len(AGENT_ORDER), ""
        if agent in AGENT_ORDER:
            return AGENT_ORDER.index(agent) + 1, agent
        return 0, agent

    def time_running(self) -> float:
        if self.thread and self.thread.is_alive():
            return self.elapsed + time.time() - self._t_start
        if not self.elapsed:
            evs = events.get_events(self.run_id)
            return sum(e["duration_s"] or 0 for e in evs if e["status"] == "done")
        return self.elapsed


def load_snapshot(run_id: str, *, output_dir: str | None = None, include_log: bool = True) -> dict:
    import json
    from pathlib import Path

    from config import OUTPUT_DIR

    if output_dir is None:
        output_dir = next((r["output_dir"] for r in events.list_runs(500) if r["run_id"] == run_id), None)
    path = Path(output_dir or OUTPUT_DIR / run_id) / "state.json"
    if not path.exists():
        return {}
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    st.setdefault("history", [])
    if include_log:
        st.setdefault("log", [e["time"] + "  " + e["agent"] + ": " + e["summary"]
                              for e in events.get_events(run_id) if e["status"] == "done"])
    return st


class RunManager:
    def __init__(self):
        self.runs: dict[str, Run] = {}
        self._submissions: dict[str, str] = {}
        self._start_lock = threading.Lock()

    def start(self, request: str, manual_review: bool = False, max_iterations: int = MAX_ITERATIONS,
              approval_points: list | None = None, fengshui_enabled: bool = True, *,
              request_fields: dict | None = None, submission_id: str | None = None) -> Run:
        with self._start_lock:
            if submission_id and submission_id in self._submissions:
                return self.runs[self._submissions[submission_id]]
            st = initial_state(request, manual_review=manual_review, max_iterations=max_iterations,
                               approval_points=approval_points, interactive=True, fengshui_enabled=fengshui_enabled,
                               request_fields=request_fields)
            run = Run(run_id=st["run_id"], request=st["user_request"])
            self.runs[run.run_id] = run
            if submission_id:
                self._submissions[submission_id] = run.run_id
            run._start(st)
            return run

    def get(self, run_id: str) -> Run:
        if run_id not in self.runs:
            # mở lại lượt cũ từ checkpointer (lịch sử thiết kế)
            run = Run(run_id=run_id, request="")
            st = run.state()
            run.request = st.get("user_request", "")
            snap = get_graph().get_state(run.config)
            pending = [i for task in snap.tasks for i in (task.interrupts or [])]
            stored = events.run_status(run_id)
            if stored in ("stopped", "error"):
                run.status = stored
            elif pending:
                run.current_node = snap.next[0] if snap.next else ""
                run.interrupt_payload = pending[0].value
                run.status = "needs_input" if run.interrupt_payload.get("clarification") else "awaiting_approval"
            else:
                run.status = ("paused" if snap.next else
                              st.get("outcome") or ("done" if st.get("final_files") else "idle"))
            self.runs[run_id] = run
        return self.runs[run_id]


manager = RunManager()
