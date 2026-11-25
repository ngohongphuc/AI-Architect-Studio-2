"""Bảng hiệu suất có thể mở đến các task và các lần thực hiện tạo số liệu."""
from datetime import date, timedelta
from math import ceil
from collections import Counter

import altair as alt
import streamlit as st

import ui_theme as ui
from config import AGENT_ORDER
from monitoring import events, performance as perf, performance_demo, tasks
from ui_common import label

SOURCE_LABELS = {"live": "Dữ liệu thật", "mock": "Mock kiểm thử", "simulation": "Mô phỏng"}
OVERVIEW = ("assigned", "accepted", "first_pass", "quality", "processing")
RESOURCES = ("completed", "scored", "completion", "repairs", "waiting", "tokens", "cost", "unit_cost")
PERIODS = {"all": "Tất cả thời gian", "last7": "7 ngày gần nhất", "last30": "30 ngày gần nhất", "custom": "Tùy chọn"}
ATTEMPT_STATUS = {"queued": "Chờ", "running": "Đang làm", "awaiting_approval": "Chờ duyệt",
                  "completed": "Hoàn thành", "error": "Lỗi", "canceled": "Hủy"}
MISSING = "Chưa có dữ liệu"

STATUS_BARS = (
    ("queued", "Chờ", "#8B9795"), ("running", "Đang làm", "#087B81"),
    ("awaiting_approval", "Chờ duyệt", "#B67218"), ("accepted", "Được nghiệm thu", "#4D8B5A"),
    ("completed", "Đã xử lý", "#537F9C"), ("error", "Lỗi", "#AE5144"), ("canceled", "Hủy", "#8B8D88"),
)


def _format(metric: str, item: perf.Metric) -> str:
    value = item.value
    if value is None:
        return MISSING
    if metric in ("first_pass", "completion"):
        return f"{value:.1%} ({item.assessed}/{item.population})"
    if metric == "quality":
        return f"{value:.1f}/{item.scale:.1f}"
    if metric in ("waiting", "processing"):
        return f"{value:.2f} giây"
    if metric in ("cost", "unit_cost"):
        value = f"{'≈ ' if item.estimated else ''}{value:.6g} USD"
    else:
        value = f"{value:,}"
    if metric in ("tokens", "cost") and item.assessed < item.population:
        return f"{value} ({item.assessed}/{item.population} lần)"
    return value


def _set_drill(agent: str, metric: str) -> None:
    st.session_state["perf_detail_agent"] = agent
    st.session_state["perf_detail_metric"] = metric


def _select(container, name: str, options, formatter, key: str):
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    chosen = container.selectbox(name, options, format_func=formatter, key=key)
    st.session_state.setdefault("perf_filter_values", {})[key] = chosen
    return chosen


def open_profile(request: dict) -> None:
    source = request.get("source", "live")
    st.session_state["perf_source"] = source
    defaults = {"period": "all", "run": request.get("run") or "", "agent": request.get("agent") or "",
                "stage": "", "model": ""}
    saved = st.session_state.setdefault("perf_filter_values", {})
    saved["perf_source"] = source
    for field, value in defaults.items():
        key = f"perf_{field}_{source}"
        saved[key] = st.session_state[key] = value
    _set_drill(defaults["agent"], "assigned")


def _filters(source: str, data: list[perf.Task], projects: dict[str, str], run_col, period_col, agent_col, advanced):
    run = _select(run_col, "Lượt thiết kế", ["", *projects], lambda item: projects.get(item, "Tất cả lượt"),
                  f"perf_run_{source}")
    period = _select(period_col, "Khoảng giao việc", list(PERIODS), PERIODS.get, f"perf_period_{source}")
    agent = _select(agent_col, "Agent", ["", *AGENT_ORDER], lambda item: label(item) if item else "Tất cả agent",
                    f"perf_agent_{source}")
    start = end = None
    today = date.today()
    if period in ("last7", "last30"):
        end = today
        start = today - timedelta(days=6 if period == "last7" else 29)
    if period == "custom":
        values = st.date_input("Ngày giao đầu tiên", value=(today - timedelta(days=29), today),
                               format="DD/MM/YYYY", key=f"perf_dates_{source}")
        if len(values) != 2:
            st.info("Chọn đủ ngày bắt đầu và kết thúc.")
            return None
        start, end = values
    stages = {row.stage: row.name for row in perf.filter_tasks(data, run=run, agent=agent)}
    stage = _select(advanced, "Loại task", ["", *stages], lambda item: stages.get(item, "Tất cả loại"),
                    f"perf_stage_{source}")
    candidates = perf.filter_tasks(data, run=run, agent=agent, stage=stage)
    models = sorted({model for task in candidates for model in task.models})
    if any(not task.models for task in candidates):
        models.append(perf.UNRECORDED_MODEL)
    model = _select(advanced, "Model", ["", *models],
                    lambda item: "Chưa ghi model" if item == perf.UNRECORDED_MODEL else item or "Tất cả model",
                    f"perf_model_{source}")
    return {"start": start, "end": end, "run": run, "agent": agent, "stage": stage, "model": model}


def _table(groups: dict, agents: list[str], metrics: tuple[str, ...], key: str) -> None:
    columns = {perf.METRICS[metric][0]: metric for metric in metrics}
    rows = [{"Agent": label(agent), **{title: _format(metric, groups[agent][metric])
                                       for title, metric in columns.items()}} for agent in agents]

    def select():
        cells = st.session_state[key]["selection"]["cells"]
        if cells:
            idx, column = cells[0]
            if 0 <= idx < len(agents) and column in columns:
                _set_drill(agents[idx], columns[column])

    st.dataframe(rows, width="stretch", hide_index=True, key=key, selection_mode="single-cell", on_select=select,
                 column_config={"Agent": st.column_config.TextColumn(width=164, pinned=True),
                                **{name: st.column_config.TextColumn(help=perf.METRICS[metric][1])
                                   for name, metric in columns.items()}})


def _sample_caption(metric: str, result: perf.Metric) -> str:
    if result.population == 0:
        return "Chưa có bản ghi tạo mẫu cho chỉ số này."
    if metric in ("processing", "waiting", "tokens", "cost", "unit_cost", "repairs"):
        return f"{result.assessed}/{result.population} lần thực hiện trong mẫu."
    return f"{result.assessed}/{result.population} task trong mẫu."


def _grade(row: dict | None) -> str:
    if row is None or row.get("earned") is None or row.get("applicable") is None:
        return MISSING
    state = "" if perf.complete_grade(row) else " · Chấm một phần"
    return f"{row['earned']}/{row['applicable']}{state}"


def _show_attempts(item: perf.Task) -> None:
    st.caption(f"Mã task {item.id} · Lượt {item.run}")

    def measurement(row: dict, key: str):
        return str(value) if perf.valid_number(value := row.get(key)) else MISSING

    st.dataframe([{
        "Lần": attempt["attempt_no"], "Trạng thái": ATTEMPT_STATUS.get(attempt["status"], MISSING),
        "Nghiệm thu": "Có" if attempt["acceptance"] == "accepted" else "Chưa nghiệm thu",
        "Điểm đã lưu": _grade(attempt), "Model": attempt.get("model") or MISSING,
        "Xử lý (giây)": measurement(attempt, "processing_s"), "Chờ (giây)": measurement(attempt, "wait_s"),
        "Token": measurement(attempt, "tokens"), "Chi phí (USD)": measurement(attempt, "cost_usd"),
        "Ước tính": "Có" if attempt.get("cost_basis") == "estimated" else "—",
        "Lỗi đã xác nhận": "Có" if perf.fault_confirmed(attempt) else "—",
    } for attempt in item.attempts], hide_index=True, width="stretch")
    for attempt in item.attempts:
        if perf.fault_confirmed(attempt):
            st.caption(f"Lần {attempt['attempt_no']} · {attempt.get('reviewer') or MISSING} (tự khai) · "
                       f"{attempt.get('reviewed_at') or MISSING}")
            st.text(attempt["agent_fault_evidence"])


def _drill(data: list[perf.Task], agents: list[str], projects: dict[str, str]) -> None:
    ui.section("Task tạo nên chỉ số")
    agent_col, metric_col = st.columns((1, 1.4))
    agent_options = ["", *agents] if len(agents) > 1 else agents
    if st.session_state.get("perf_detail_agent") not in agent_options:
        st.session_state["perf_detail_agent"] = agent_options[0]
    agent = agent_col.selectbox("Agent trong chi tiết", agent_options, key="perf_detail_agent",
                                format_func=lambda item: label(item) if item else "Tất cả agent")
    metric = metric_col.selectbox("Chỉ số trong chi tiết", list(perf.METRICS), key="perf_detail_metric",
                                  format_func=lambda item: perf.METRICS[item][0])
    group = [item for item in data if not agent or item.agent == agent]
    result = perf.summarize(group)[metric]
    st.markdown(f"**{perf.METRICS[metric][0]} · {_format(metric, result)}**")
    st.caption(perf.METRICS[metric][1] + " " + _sample_caption(metric, result))
    if metric == "unit_cost":
        st.caption(f"Mẫu số tính chi phí đơn vị gồm {len(result.task_ids)} task được nghiệm thu.")
    included = {item.id: item for item in group if item.id in result.task_ids}
    if not included:
        st.caption("Chưa có task đóng góp cho chỉ số này.")
        return
    st.dataframe([{
        "Task": item.name, "Lượt": projects.get(item.run, item.run), "Agent": label(item.agent),
        "Ngày giao": perf.local_day(item.first["assigned_at"]), "Số lần": len(item.attempts),
        "Lần đầu nghiệm thu": "Có" if item.first["attempt_no"] == 1 and item.first["acceptance"] == "accepted" else "Chưa",
        "Điểm lần đầu": _grade(item.first), "Điểm lần cuối nghiệm thu": _grade(item.final),
        "Đóng góp": _format(metric, perf.summarize([item])[metric]),
    } for item in included.values()], width="stretch", hide_index=True)
    key = "perf_drill_task"
    if st.session_state.get(key) not in included:
        st.session_state[key] = next(iter(included))
    chosen = st.selectbox("Mở các lần thực hiện của task", list(included), key=key,
                          format_func=lambda ident: f"{included[ident].name} · {projects.get(included[ident].run, included[ident].run)}")
    _show_attempts(included[chosen])


def _charts(data: list[perf.Task], groups: dict, agents: list[str]) -> None:
    quality, timing = st.columns(2)
    labels = [label(agent) for agent in agents]
    with quality:
        ui.section("Điểm chất lượng theo thời gian")
        st.caption("Ngày nghiệm thu của lần cuối được nghiệm thu (bước tự động: ngày xử lý xong), với điểm gốc đã chấm đủ.")
        points = [{**row, "name": label(row["agent"])} for row in perf.quality_series(data)]
        if points:
            days = [date.fromisoformat(row["day"]) for row in points]
            tick_step = max(1, ceil((max(days) - min(days)).days / 5))
            chart = alt.Chart(alt.Data(values=points)).mark_line(point=True).encode(
                x=alt.X("day:T", title="Ngày nghiệm thu", scale=alt.Scale(type="utc"),
                        axis=alt.Axis(format="%d/%m/%Y", tickCount=alt.TimeIntervalStep(interval="day", step=tick_step))),
                y=alt.Y("earned:Q", title="Điểm trung bình", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("name:N", title="Agent", sort=labels),
                tooltip=[alt.Tooltip("name:N", title="Agent"), alt.Tooltip("day:T", title="Ngày", format="%d/%m/%Y"),
                         alt.Tooltip("earned:Q", title="Điểm TB", format=".2f"),
                         alt.Tooltip("applicable:Q", title="Tối đa TB", format=".2f"),
                         alt.Tooltip("tasks:Q", title="Task đã chấm đủ")],
            )
            st.altair_chart(chart, width="stretch")
        else:
            st.info(MISSING + " điểm đầy đủ kèm ngày nghiệm thu.")
    with timing:
        ui.section("Thời gian theo agent")
        st.caption("Trung vị theo các lần có mốc thời gian. Thứ tự theo vai trò.")
        bars = [{"name": label(agent), "kind": kind, "seconds": item.value, "sample": item.assessed}
                for agent in agents for name, kind in (("processing", "Xử lý"), ("waiting", "Chờ"))
                if (item := groups[agent][name]).value is not None]
        if bars:
            st.altair_chart(alt.Chart(alt.Data(values=bars)).mark_bar().encode(
                y=alt.Y("name:N", title=None, sort=labels), yOffset="kind:N",
                x=alt.X("seconds:Q", title="Giây"),
                color=alt.Color("kind:N", title="Thời gian", scale=alt.Scale(domain=["Xử lý", "Chờ"],
                                                                            range=["#167D8D", "#C89868"])),
                tooltip=[alt.Tooltip("name:N", title="Agent"), alt.Tooltip("kind:N", title="Loại"),
                         alt.Tooltip("seconds:Q", title="Giây", format=".2f"),
                         alt.Tooltip("sample:Q", title="Số lần có dữ liệu")],
            ), width="stretch")
        else:
            st.info(MISSING + " thời gian xử lý và chờ.")


def _activity_cards(data: list[perf.Task]) -> None:
    status_column, time_column = st.columns([1, 1.12], gap="medium")
    counts = Counter("accepted" if task.attempts[-1]["acceptance"] == "accepted" else task.attempts[-1]["status"]
                     for task in data)
    with status_column.container(border=True, key="status_distribution"):
        ui.section("Công việc theo trạng thái")
        rows = []
        for key, title, color in STATUS_BARS:
            amount = counts[key]
            if amount or key in ("queued", "running", "awaiting_approval", "accepted"):
                rows.append(f'<div class="aa-status-row"><span>{ui.esc(title)}</span>'
                            f'<span class="aa-status-track" aria-hidden="true"><span style="width:{100 * amount / len(data):.4f}%;'
                            f'background:{color}"></span></span><b>{amount}</b></div>')
        ui.html_block(f'<div class="aa-status-bars">{"".join(rows)}</div>')
        st.caption("Trạng thái của lần thực hiện mới nhất trong mỗi task.")
    with time_column.container(border=True, key="task_activity"):
        ui.section("Task được giao và nghiệm thu")
        assigned = Counter(perf.local_day(task.first["assigned_at"]) for task in data)
        accepted = Counter(perf.local_day(attempt["decision_at"]) for task in data
                           if (attempt := next((row for row in task.attempts if row["acceptance"] == "accepted"), None)))
        days = sorted(day for day in (assigned.keys() | accepted.keys()) if day is not None)
        if not days:
            st.info("Chưa có mốc thời gian để vẽ.")
            return
        points = [{"date": day.isoformat(), "kind": kind, "count": tracker[day]}
                  for day in days for kind, tracker in (("Được giao", assigned), ("Nghiệm thu", accepted))]
        chart = alt.Chart(alt.Data(values=points)).mark_line(point=True, strokeWidth=2.25).encode(
            x=alt.X("date:T", title=None, scale=alt.Scale(type="utc"),
                    axis=alt.Axis(format="%d/%m", tickCount=alt.TimeIntervalStep(
                        interval="day", step=max(1, ceil((days[-1] - days[0]).days / 6))))),
            y=alt.Y("count:Q", title=None, axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("kind:N", title=None, scale=alt.Scale(domain=["Được giao", "Nghiệm thu"],
                                                                  range=["#087B81", "#54749D"]),
                            legend=alt.Legend(orient="bottom", direction="horizontal")),
            tooltip=[alt.Tooltip("date:T", title="Ngày", format="%d/%m/%Y"),
                     alt.Tooltip("kind:N", title="Loại"), alt.Tooltip("count:Q", title="Số task")],
        ).configure(background="transparent").configure_view(stroke=None).configure_axis(
            gridColor="#E8ECE9", labelColor="#4D6169", domainColor="#B8C4C0", tickColor="#B8C4C0",
        ).configure_legend(labelColor="#4D6169")
        st.altair_chart(chart, width="stretch", height=176, theme=None, alt="Số task được giao và nghiệm thu theo ngày")
        st.caption("Đếm mỗi task một lần theo ngày giao đầu tiên hoặc ngày nghiệm thu đầu tiên.")


def show_performance() -> None:
    for key, value in st.session_state.get("perf_filter_values", {}).items():
        st.session_state.setdefault(key, value)
    run_col, period_col, agent_col, options_col = st.columns((1.25, 1, 1, 1.04), vertical_alignment="bottom")
    advanced = options_col.popover("Tùy chỉnh báo cáo", icon=":material/tune:", width="stretch")
    source = _select(advanced, "Nguồn dữ liệu", list(SOURCE_LABELS), SOURCE_LABELS.get, "perf_source")
    data = perf.load(source)
    projects = {}
    for run in events.list_runs(None, recent_activity=True, data_source=source):
        ident, name = run["run_id"], run["summary"].get("ten_du_an")
        projects[ident] = f"{name} · {ident}" if name else ident
    demo = source == "mock" and not data
    if demo:
        data = performance_demo.sample()
        projects = performance_demo.RUNS
    if source == "simulation" and not data:
        agent = st.session_state.get("perf_agent_simulation")
        if agent in AGENT_ORDER:
            ui.section(label(agent))
        st.info("Chưa có dữ liệu hiệu suất. Mô phỏng văn phòng 3D chạy trong trình duyệt và không ghi task.")
        return
    filters = _filters(source, data, projects, run_col, period_col, agent_col, advanced)
    if filters is None:
        return
    data = perf.filter_tasks(data, **filters)
    start, end = filters["start"], filters["end"]
    interval = f"{start:%d/%m/%Y} đến {end:%d/%m/%Y}" if start is not None else "Tất cả thời gian"
    if source == "mock":
        ui.html_block(ui.pill("Dữ liệu minh họa", "warning"))
    elif source == "simulation":
        ui.html_block(ui.pill("Mô phỏng", "info"))
    if demo:
        st.caption("Mẫu mock cố định. Chọn tất cả thời gian để xem dữ liệu tháng 1/2025.")
    st.caption(f"Kỳ giao việc · {interval} theo ngày địa phương. Mỗi task lấy ngày giao lần đầu và giữ toàn bộ các lần thực hiện.")
    if filters["model"]:
        st.caption("Bộ lọc model chọn task có lần thực hiện phù hợp. Điểm, token và chi phí vẫn bao gồm các lần cùng task.")
    if not data:
        st.info("Chưa có dữ liệu task trong phạm vi đã chọn.")
        return

    summary = perf.summarize(data)
    groups = perf.by_agent(data)
    agents = [filters["agent"]] if filters["agent"] else AGENT_ORDER
    tiles = (("assigned", "Task đã giao", "clipboard", "brand"),
             ("accepted", "Được nghiệm thu", "check", "success"),
             ("first_pass", "Đạt ngay lần đầu", "target", "warning"),
             ("quality", "Điểm chất lượng", "shield", "info"))
    with st.container(key="performance_cards"):
        for column, (metric, title, glyph, tone) in zip(st.columns(4), tiles, strict=True):
            item = summary[metric]
            value = _format(metric, item)
            note = ""
            if metric == "first_pass" and item.value is not None:
                value = f"{item.value:.1%}"
                note = f"{item.assessed}/{item.population} task đã giao"
            elif metric == "quality":
                note = f"{item.assessed}/{item.population} task nghiệm thu đã chấm đủ" if item.population else "Chưa có nghiệm thu"
            with column.container(key=f"perf_tile_{metric}"):
                ui.html_block(ui.kpi(title, value, glyph, tone, note, compact=item.value is None))
                st.button(f"{title} · {value}", key=f"perf_top_{metric}", width="stretch",
                          on_click=_set_drill, args=(filters["agent"], metric))

    _activity_cards(data)
    with st.container(border=True, key="perf_agents_summary"):
        ui.section("Tổng hợp theo agent", "Bấm một ô chỉ số để xem các task trong mẫu.")
        scope = hash((source, *filters.values(), st.session_state.get("perf_detail_agent"),
                      st.session_state.get("perf_detail_metric")))
        _table(groups, agents, OVERVIEW, f"perf_quality_table_{scope}")
        with st.expander("Chất lượng, tỷ lệ và chi phí chi tiết"):
            _table(groups, agents, RESOURCES, f"perf_resources_table_{scope}")
    with st.container(border=True, key="perf_drilldown"):
        _drill(data, agents, projects)
    with st.expander("Phân tích chất lượng và thời gian"):
        _charts(data, groups, agents)
    with st.expander("Công thức và mẫu số"):
        st.markdown("\n".join(f"- **{title}** · {formula}" for title, formula in perf.METRICS.values()))
        st.caption("Điểm gốc giữ nguyên thang của từng task. Bảng theo thứ tự vai trò. "
                   "Chi phí chưa đủ bảng kê hiển thị phần đã ghi hoặc chưa có dữ liệu.")
    st.download_button("Xuất CSV dữ liệu đang lọc", perf.csv_export(data, source),
                       f"hieu_suat_{source}.csv", "text/csv", icon=":material/download:", on_click="ignore")
