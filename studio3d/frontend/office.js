import { activity, countKinds, elapsed, KINDS } from "./status.mjs";

const $ = (id) => document.getElementById(id);
const buttons = ["zoom-out", "zoom-in", "reset", "enlarge"];
const views = ["scene", "flow"];
const statuses = {
  waiting: "Chờ", idle: "Chưa chọn lượt", running: "Đang xử lý", revising: "Đang xử lý lại",
  done: "Đã xử lý", paused: "Tạm dừng", stopped: "Đã dừng", error: "Lỗi", skipped: "Đã tắt",
  awaiting_approval: "Chờ duyệt", needs_input: "Cần bổ sung yêu cầu", feedback: "Đã gửi phản hồi",
  not_passed: "Chưa đạt",
};
const workStates = new Set(["running", "revising"]);
const lounge = {id: "lounge", name: "Góc nghỉ", description: "Chỗ nghỉ cạnh lối đi dành cho hoạt ảnh khi rảnh."};
const storageKey = "ai-architect-office-3d.v1";
const motionQuery = matchMedia("(prefers-reduced-motion: reduce)");
const state = {
  live: null, data: null, mode: "live", visit: null, managed: false,
  cursor: 0, pendingIds: new Set(), deliveryInbox: [], view: "all", selection: {},
  workspace: "scene", panelCollapsed: false, enlarged: false,
  scene: null, loading: false, failure: "", wantsList: false,
};

function readPreferences() {
  try { return JSON.parse(sessionStorage.getItem(storageKey)) || {}; } catch { return {}; }
}

const preferences = readPreferences();
state.view = preferences.view || "all";
state.selection = preferences.selection || {};
state.wantsList = preferences.list === true;
state.workspace = views.includes(preferences.workspace) ? preferences.workspace : "scene";
state.panelCollapsed = preferences.panelCollapsed === true;

function remember(changes) {
  Object.assign(preferences, changes);
  try { sessionStorage.setItem(storageKey, JSON.stringify(preferences)); } catch { /* trình duyệt có thể chặn bộ nhớ */ }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function trigger(className, text, action) {
  const node = element("button", className, text);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}

function pressed(node, value) {
  node.setAttribute("aria-pressed", String(value));
}

function statusBadge(node, value, description = statuses[value] || value) {
  if (node.dataset.status !== value) node.dataset.status = value;
  if (node.textContent !== description) node.textContent = description;
  return node;
}

function postStreamlit(type, detail = {}) {
  window.parent.postMessage({isStreamlitMessage: true, type, ...detail}, window.location.origin);
}

let lastHeight;
function fitFrame() {
  const height = Math.ceil($("office").getBoundingClientRect().height) + 3;
  if (height === lastHeight) return;
  lastHeight = height;
  postStreamlit("streamlit:setFrameHeight", {height});
}

new ResizeObserver(fitFrame).observe($("office"));

function agentBadge(node, agent) {
  const {kind, label} = activity(agent, state.data.run);
  node.dataset.kind = kind;
  return statusBadge(node, "agent", label);
}

const DESK_TEXT = {working: "Đang làm", user: "Chờ bạn", error: "Lỗi", paused: "Tạm dừng", next: "Sắp tới",
  queued: "Chờ lượt", idle: "Rảnh"};

function deskLabel(badge, agent) {
  const {kind, label} = activity(agent, state.data.run);
  badge.dataset.kind = kind;
  badge.title = agent.name + " · " + label;
  badge.setAttribute("aria-label", badge.title);
  const text = agent.short + (DESK_TEXT[kind] ? " · " + DESK_TEXT[kind] : "");
  if (badge.textContent !== text) {
    badge.textContent = text;
    labelSizes.delete(agent.id);
  }
}

const roomButtons = new Map();
const deskLabels = new Map();
const listEntries = new Map();

function agentById(id) {
  return state.data?.agents.find((agent) => agent.id === id);
}

function roomById(id) {
  if (id === lounge.id) return lounge;
  return state.data?.rooms.find((room) => room.id === id);
}

function agentChoice(agent) {
  const b = trigger("agent-choice", "", () => choose({agent: agent.id}));
  const dot = element("span", "agent-color");
  dot.style.setProperty("--agent-color", agent.color);
  const chip = agentBadge(element("span", "status"), agent);
  b.append(dot, element("span", "", agent.name), chip);
  pressed(b, state.selection.agent === agent.id);
  return {button: b, chip};
}

function buildNavigation() {
  const options = [{id: "all", name: "Toàn cảnh"}, ...state.data.rooms, lounge];
  for (const room of options) {
    const button = trigger("room-button", room.name, () => focusRoom(room.id));
    roomButtons.set(room.id, button);
    $("room-views").append(button);
  }
  for (const agent of state.data.agents) {
    const badge = trigger("desk-label", agent.short, () => choose({agent: agent.id}));
    badge.style.setProperty("--agent-color", agent.color);
    badge.hidden = true;
    deskLabels.set(agent.id, badge);
    $("desk-labels").append(badge);
  }
  for (const room of state.data.rooms) {
    $("agent-list").append(element("h3", "", room.name));
    for (const agent of state.data.agents.filter((item) => item.room === room.id)) {
      const choice = agentChoice(agent);
      $("agent-list").append(choice.button);
      listEntries.set(agent.id, choice);
    }
  }
}

function updateNavigation() {
  const room = roomById(state.view);
  const view = state.view === "showcase" ? "Mô hình dự án" : room?.name || "Toàn cảnh";
  $("view-label").textContent = view;
  for (const [id, button] of roomButtons) pressed(button, state.view === id);
  for (const agent of state.data.agents) {
    const badge = deskLabels.get(agent.id);
    const choice = listEntries.get(agent.id);
    pressed(badge, state.selection.agent === agent.id);
    deskLabel(badge, agent);
    pressed(choice.button, state.selection.agent === agent.id);
    agentBadge(choice.chip, agent);
  }
  for (const button of document.querySelectorAll(".workspace-panel [data-agent]")) {
    pressed(button, state.selection.agent === button.dataset.agent);
  }
  renderBoard();
  const model = state.data.geometry;
  $("project-model").textContent = model
    ? "Mô hình khối · " + model.floors.length + " tầng" : "Mô hình minh họa";
}

function choose(selection) {
  state.selection = selection;
  if (selection.agent && state.panelCollapsed) togglePanel(false);
  remember({selection});
  state.scene?.select(selection);
  updateNavigation();
  renderInspector(true);
}

function resetCamera() {
  state.view = "all";
  remember({view: "all"});
  updateNavigation();
  state.scene?.focus("all");
}

function focusRoom(id) {
  state.view = id;
  remember({view: state.view});
  choose(id === "all" ? {} : {room: id});
  state.scene?.focus(id);
}

function dataValues(data) {
  if (data == null) return element("span", "note", "Chưa xác định");
  if (typeof data !== "object") return element("span", "", typeof data === "boolean" ? (data ? "Có" : "Không") : data);
  const entries = Object.entries(data);
  if (!entries.length) return element("span", "note", "Chưa có dữ liệu");
  const list = element("dl", "data-values");
  for (const [key, value] of entries) {
    const label = Array.isArray(data) ? "Mục " + (Number(key) + 1) : key.replaceAll("_", " ");
    const term = element("dt", "", label);
    const detail = element("dd");
    if (value != null && typeof value === "object") {
      const group = element("details", "data-group");
      group.append(element("summary", "", label), dataValues(value));
      list.append(element("dt", "nested-label"), element("dd", "nested-value"));
      list.lastChild.append(group);
    } else {
      detail.append(dataValues(value));
      list.append(term, detail);
    }
  }
  return list;
}

function inspectorSection(key, title, content) {
  const detail = element("details", "inspector-section");
  detail.dataset.section = key;
  detail.append(element("summary", "", title));
  detail.addEventListener("toggle", () => {
    if (detail.open && detail.childElementCount === 1) detail.append(content());
  });
  return detail;
}

function reviewCriteria(rows) {
  const group = element("div", "review-criteria");
  for (const [index, row] of rows.entries()) {
    const detail = element("details", "review-criterion");
    detail.dataset.criterion = row.criterion + ":" + index;
    detail.dataset.tone = row.tone;
    const summary = element("summary", "", row.criterion);
    summary.append(element("span", "review-status", row.status));
    detail.append(summary);
    for (const [title, value] of [["Lý do", row.reason], ["Nguồn", row.source], ["Phạm vi", row.scope],
      ["Phương án", row.actual], [row.tone === "warning" ? "Giá trị đối chiếu tham khảo" : "Ngưỡng phép kiểm", row.threshold],
      ["Trích dẫn", row.excerpt], ["Dữ liệu còn thiếu", row.missing?.join(" · ")], ["Cách bổ sung", row.action]]) {
      if (value && value !== "—") detail.append(element("p", "note", title + " · " + value));
    }
    group.append(detail);
  }
  return group;
}

function agentInspector(agent) {
  const nodes = [];
  const room = roomById(agent.room);
  const overline = element("div", "overline");
  const dot = element("span", "agent-color");
  dot.style.setProperty("--agent-color", agent.color);
  overline.append(dot, element("span", "", room.name));
  nodes.push(overline, element("h2", "", agent.name), agentBadge(element("span", "status"), agent),
    element("p", "note activity-detail", activity(agent, state.data.run).detail));
  nodes.push(element("p", "description", agent.task));
  if (state.managed) nodes.push(trigger("control profile-link", "Mở hồ sơ hiệu suất", () => {
    const nonce = window.crypto?.randomUUID?.() || String(Date.now()) + "-" + Math.random().toString(36).slice(2);
    postStreamlit("streamlit:setComponentValue", {dataType: "json",
      value: {action: "performance", agent: agent.id, nonce}});
  }));
  const group = element("div", "agent-result");
  group.append(element("h3", "", "Kết quả gần nhất"));
  group.append(element("p", "note", agent.summary || "Chưa xác định."));
  if (agent.version != null) group.append(element("p", "note", "Phiên bản " + agent.version));
  nodes.push(group);
  if (agent.issues.length) {
    const list = element("ul", "issues");
    for (const issue of agent.issues) list.append(element("li", "", issue));
    nodes.push(element("h3", "", "Lỗi và phản hồi"), list);
  } else nodes.push(element("p", "note no-issues", "Chưa ghi nhận lỗi hoặc phản hồi."));
  nodes.push(inspectorSection("input", "Đầu vào", () => dataValues(agent.input)),
    inspectorSection("output", "Đầu ra", () => dataValues(agent.output)),
    inspectorSection("technical", "Dữ liệu kỹ thuật", () => {
      const data = element("pre", "record", JSON.stringify({input: agent.input, output: agent.output}, null, 2));
      data.tabIndex = 0;
      return data;
    }));
  if (state.data.agents.some((peer) => peer.id !== agent.id && peer.room === agent.room)) {
    const choices = element("div", "agent-choices");
    for (const peer of state.data.agents.filter((item) => item.id !== agent.id && item.room === agent.room)) {
      choices.append(agentChoice(peer).button);
    }
    nodes.push(choices);
  }
  return nodes;
}

function roomInspector(room) {
  if (state.selection.room === "showcase") {
    const model = state.data.geometry;
    const note = model ? (
      "Mô hình khối sử dụng tọa độ phòng và cao độ tầng của mặt bằng hiện hành."
    ) : "Mô hình minh họa. Mặt bằng hiện hành chưa có đủ dữ liệu hình học để dựng mô hình khối.";
    const nodes = [element("h2", "", "Mô hình dự án"), element("p", "description", note)];
    if (model) {
      const format = new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 2});
      nodes.push(element("p", "note", model.floors.length + " tầng · " + format.format(model.width) + " × "
        + format.format(model.depth) + " m (khối xây dựng)"));
    }
    return nodes;
  }
  const title = room?.name || "Các khu làm việc";
  const description = room?.description || "Chọn một khu hoặc agent để xem công việc trong lượt thiết kế.";
  const agents = room ? state.data.agents.filter((agent) => agent.room === room.id) : state.data.agents;
  const list = element("div", "agent-choices");
  for (const agent of agents) list.append(agentChoice(agent).button);
  return [element("h2", "", title), element("p", "description", description), list];
}

let inspectorKey;
function renderInspector(reset = false) {
  const agent = agentById(state.selection.agent);
  const room = roomById(state.selection.room);
  const peers = state.data.agents.filter((peer) => peer.room === agent?.room || peer.room === room?.id)
    .map((peer) => peer.status);
  const key = JSON.stringify([state.mode, state.managed, state.selection, agent, peers, state.data.run.status, state.data.run.upcoming,
    state.selection.room === "showcase" ? state.data.geometry : null,
    !agent && !room ? state.data.agents.map((peer) => peer.status) : null]);
  if (!reset && key === inspectorKey) return;
  inspectorKey = key;
  const panel = $("inspector");
  const opened = reset ? [] : Array.from(panel.querySelectorAll("[data-section][open]"), (d) => d.dataset.section);
  const focus = panel.contains(document.activeElement) ? document.activeElement.closest("[data-section]")?.dataset.section : null;
  const previousPosition = panel.scrollTop;
  panel.replaceChildren(...(agent ? agentInspector(agent) : roomInspector(room)));
  for (const detail of panel.querySelectorAll("[data-section]")) {
    detail.open = opened.includes(detail.dataset.section);
    if (detail.dataset.section === focus) detail.querySelector("summary").focus({preventScroll: true});
  }
  panel.scrollTop = reset ? 0 : previousPosition;
}

function transferText(event) {
  const source = agentById(event.from)?.name || "Chưa xác định";
  const target = event.to === "showcase" ? "Bàn trưng bày dự án" : agentById(event.to)?.name || "Chưa xác định";
  return source + " → " + target;
}

function transferType(event) {
  return event.pending ? "Chờ duyệt" : event.feedback ? "Trả sửa" : event.approved ? "Chuyển sau duyệt" : "Bàn giao";
}

let deliveryKey;
function showDeliveries(jobs) {
  const host = $("scene-deliveries");
  const key = JSON.stringify([state.visit, jobs.map(({event, phase}) => [event.id, phase])]);
  if (key === deliveryKey) return;
  deliveryKey = key;
  host.hidden = !jobs.length;
  host.replaceChildren(...jobs.map(({event, phase}) => {
    const badge = element("div", "scene-delivery");
    badge.dataset.feedback = String(Boolean(event.feedback));
    const verb = phase === "walking" ? "Đang mang hồ sơ" : phase === "exchanging" ? "Đang trao hồ sơ" : "Đã trao hồ sơ";
    badge.append(element("strong", "", verb + " · " + transferText(event)),
      element("span", "", (event.feedback ? "Trả sửa · " : "") + event.summary));
    return badge;
  }));
}

function transferLabel(event) {
  const panel = $("transfer");
  panel.dataset.feedback = String(Boolean(event?.feedback));
  const route = $("transfer-route"), summary = $("transfer-summary"), time = $("transfer-time");
  if (!event) {
    route.textContent = "Chuyển việc";
    summary.textContent = "Chưa có bàn giao trong lượt này.";
    time.hidden = true;
    return;
  }
  route.textContent = transferType(event) + " · " + transferText(event);
  summary.textContent = event.summary;
  time.textContent = event.time || "";
  time.hidden = !event.time;
}

let handoffKey;
function renderHandoffs() {
  if (!state.data) return;
  const filter = $("handoff-filter").value;
  const transfers = state.data.transfers;
  const key = JSON.stringify([state.visit, filter, transfers]);
  if (key === handoffKey) return;
  handoffKey = key;
  const rows = transfers.filter((item) => filter === "all" ||
    filter === (item.pending ? "pending" : item.feedback ? "feedback" : "normal")).slice().reverse();
  const items = rows.map((item) => {
    const row = element("li");
    row.dataset.feedback = String(Boolean(item.feedback));
    row.append(element("time", "", item.time || "Chưa xác định"),
      element("strong", "", transferType(item) + " · " + transferText(item)),
      element("p", "note", item.summary || "Chưa xác định"));
    return row;
  });
  $("handoff-rows").replaceChildren(...(items.length ? items : [
    element("li", "note", transfers.length ? "Không có sự kiện phù hợp." : "Chưa ghi nhận bàn giao."),
  ]));
}

let qualityKey;
function renderQuality() {
  const quality = state.data.quality;
  $("quality").hidden = !quality || state.mode === "demo";
  if ($("quality").hidden) return;
  const key = JSON.stringify([state.visit, quality]);
  if (key === qualityKey) return;
  qualityKey = key;
  $("quality-status").replaceChildren(
    element("span", "", "Kiểm tra kỹ thuật · " + quality.technical),
    element("span", "", "Xác minh quy chuẩn · " + quality.regulatory));
  const findings = quality.findings;
  const details = $("quality-details");
  details.hidden = !findings.length;
  $("quality-summary").hidden = findings.length > 0 || !quality.preliminary;
  const unknown = quality.unverified ? quality.unverified + " nội dung cần xác minh" : "";
  const actionNeeded = findings.length - quality.unverified;
  $("quality-title").textContent = [
    quality.preliminary ? "Đã tạo phương án sơ bộ" : "",
    unknown,
    actionNeeded ? actionNeeded + " nội dung cần xem lại" : "",
  ].filter(Boolean).join(" · ");
  const openRows = new Set(Array.from($("quality-findings").querySelectorAll("[open]"), (row) => row.dataset.criterion));
  const criteria = reviewCriteria(findings);
  for (const row of criteria.children) row.open = openRows.has(row.dataset.criterion);
  $("quality-findings").replaceChildren(criteria);
}

const workflowStages = [
  {label: "Tiếp nhận", agents: ["project_manager", "requirements_analyst"], note: "Chủ nhiệm tiếp nhận brief trước khi giao thiết kế."},
  {label: "Thiết kế", agents: ["concept_architect", "architect"], note: "So sánh phương án và chi phí trước khi triển khai."},
  {label: "Triển khai", agents: ["drafter"]},
  {label: "Thẩm định", agents: ["fengshui_advisor", "reviewer"], optional: true},
  {label: "Bàn giao", agents: ["cost_estimator", "final_reviewer"], note: "Chủ nhiệm tổng hợp giữa dự toán và kiểm tra hồ sơ."},
];

function workflowNode(id, latest) {
  const agent = agentById(id);
  const button = trigger("flow-agent", "", () => choose({agent: id}));
  button.dataset.agent = id;
  const dot = element("span", "agent-color");
  dot.style.setProperty("--agent-color", agent.color);
  button.append(dot, element("span", "flow-name", agent.name), agentBadge(element("span", "status"), agent));
  const active = workStates.has(agent.status)
    || (state.data.run.status === "running" && state.data.run.current === id);
  if (active) button.classList.add("is-current");
  if (latest?.from === id || latest?.to === id) button.classList.add("is-handoff");
  pressed(button, state.selection.agent === id);
  return button;
}

function flowNotice(className, label, event) {
  const notice = element("div", className);
  notice.append(element("strong", "", label), element("p", "", transferText(event)),
    element("p", "note", event.summary || "Chưa xác định"));
  return notice;
}

function drawWorkflow() {
  const latest = state.data.transfers.at(-1);
  const returned = state.data.transfers.findLast((event) => event.feedback);
  const diagram = element("div", "flow-diagram");
  for (const stage of workflowStages) {
    const row = element("section", "flow-stage");
    row.append(element("h3", "", stage.label));
    const lane = element("div", "flow-lane");
    for (const [n, id] of stage.agents.entries()) {
      if (n) {
        const arrow = element("span", "flow-arrow", "→");
        arrow.setAttribute("aria-hidden", "true");
        if (latest?.from === stage.agents[n - 1] && latest?.to === id) arrow.classList.add("is-handoff");
        lane.append(arrow);
      }
      lane.append(workflowNode(id, latest));
    }
    row.append(lane);
    if (stage.optional) {
      const branches = element("div", "branch-paths");
      const fengshui = state.data.run.fengshui_enabled;
      for (const [enabled, path] of [[true, "Bật · Phong thủy → Kiểm định → Dự toán"],
        [false, "Tắt · Kiểm định → Dự toán"]]) {
        const branch = element("span", "flow-branch", path);
        branch.classList.toggle("is-taken", fengshui === enabled);
        branches.append(branch);
      }
      row.append(branches);
    } else if (stage.note) row.append(element("p", "note", stage.note));
    diagram.append(row);
  }
  const handoff = latest ? flowNotice(latest.feedback ? "flow-feedback" : "flow-handoff",
    "Bàn giao gần nhất · " + transferType(latest), latest) : element("p", "note", "Chưa ghi nhận bàn giao.");
  const feedback = returned && returned !== latest ? flowNotice("flow-feedback", "Đường phản hồi gần nhất", returned)
    : returned ? null : element("p", "note", "Chưa ghi nhận lượt trả sửa.");
  return [handoff, diagram, ...(feedback ? [feedback] : [])];
}

let boardKey;
function renderBoard() {
  const {agents, helpers = [], run} = state.data;
  const everyone = [...agents, ...helpers];
  const key = JSON.stringify([state.selection.agent, run.id, run.status, run.upcoming,
    everyone.map((a) => [a.id, a.name, a.status, a.step, a.since, a.runs, a.version, a.status === "error" && a.summary])]);
  if (key === boardKey) return;
  boardKey = key;
  const counts = countKinds(everyone, run);
  $("board-counts").replaceChildren(...Object.entries(KINDS)
    .filter(([kind]) => counts.get(kind) || kind === "working")
    .map(([kind, name]) => {
      const chip = element("span", "status", counts.get(kind) + " " + name.toLowerCase());
      chip.dataset.kind = counts.get(kind) ? kind : "idle";
      return chip;
    }));
  const focused = document.activeElement?.closest?.(".board-card")?.dataset.agent;
  $("board-cards").replaceChildren(...everyone.map((agent) => {
    const {kind, detail} = activity(agent, run);
    const custom = !agent.color;
    const card = custom ? element("div", "board-card") : trigger("board-card", "", () => choose({agent: agent.id}));
    card.dataset.kind = kind;
    card.dataset.agent = agent.id;
    const dot = element("span", "agent-color");
    dot.style.setProperty("--agent-color", agent.color || "#7b8794");
    const head = element("span", "board-name");
    head.append(dot, element("span", "", agent.name));
    if (custom) head.append(element("span", "board-tag", "tùy biến"));
    const note = element("span", "board-detail", detail);
    if (agent.since) {
      const time = element("span", "board-time", elapsed(agent.since));
      time.dataset.since = agent.since;
      note.append(detail ? " · " : "", time);
    }
    card.append(head, agentBadge(element("span", "status"), agent), note);
    if (!custom) pressed(card, state.selection.agent === agent.id);
    return card;
  }));
  if (focused) $("board-cards").querySelector('button[data-agent="' + focused + '"]')?.focus({preventScroll: true});
}

setInterval(() => {
  for (const node of document.querySelectorAll("[data-since]")) node.textContent = elapsed(node.dataset.since);
}, 1000);

let flowKey;
function renderWorkspace() {
  if (state.workspace !== "flow") return;
  const data = state.data;
  const key = JSON.stringify([state.visit, data.agents.map((a) => a.status), data.run.current, data.run.status, data.run.upcoming, data.run.fengshui_enabled,
    data.transfers.at(-1), data.transfers.findLast((event) => event.feedback)]);
  if (flowKey === key) return;
  flowKey = key;
  const panel = $("flow-view");
  const focused = panel.contains(document.activeElement) ? document.activeElement.dataset.agent : null;
  panel.replaceChildren(...drawWorkflow());
  if (focused) panel.querySelector('[data-agent="' + focused + '"]')?.focus({preventScroll: true});
}

function showWorkspace(view) {
  state.workspace = view;
  remember({workspace: view});
  for (const item of views) {
    const tab = $("tab-" + item);
    tab.setAttribute("aria-selected", String(view === item));
    tab.tabIndex = view === item ? 0 : -1;
    $(item + "-view").hidden = view !== item;
  }
  if (state.data) {
    renderWorkspace();
    updateNavigation();
    updateLayout();
    if (view === "scene") ensureScene();
  }
}

function togglePanel(collapsed) {
  state.panelCollapsed = collapsed;
  remember({panelCollapsed: collapsed});
  $("office").classList.toggle("panel-collapsed", collapsed);
  $("inspector").hidden = collapsed;
  $("panel-toggle").setAttribute("aria-expanded", String(!collapsed));
  $("panel-toggle").textContent = collapsed ? "Mở bảng chi tiết" : "Thu gọn chi tiết";
  fitFrame();
}

function setSceneError(message) {
  state.failure = message;
  state.scene?.dispose();
  state.scene = null;
  $("canvas-slot").replaceChildren();
  updateLayout();
}

function reducedMotion() {
  return preferences.motion ?? motionQuery.matches;
}

function stopAnimatedEffects() {
  return reducedMotion() || (state.mode === "demo" && !demo.playing && demo.index < script.length);
}

function idleActivity() {
  return preferences.idleActivity !== false;
}

function syncMotionControls() {
  const toggle = $("idle-activity");
  pressed(toggle, idleActivity());
  pressed($("motion"), reducedMotion());
  toggle.title = reducedMotion() ? "Hoạt ảnh tạm ngừng khi bật Giảm chuyển động."
    : idleActivity() ? "Tắt đi dạo và đưa agent về bàn."
      : "Bật đi dạo, nghỉ hoặc xem mô hình khi rảnh.";
}

function updateLayout() {
  const list = state.wantsList || Boolean(state.failure);
  const active = state.workspace === "scene";
  const canvas = !list && (state.scene || state.loading);
  $("canvas-slot").hidden = !canvas;
  $("desk-labels").hidden = list || !state.scene;
  if (list || !state.scene) showDeliveries([]);
  $("stage-caption").hidden = list || !state.scene;
  $("agent-list").hidden = !list;
  $("agent-list").classList.toggle("has-message", Boolean(state.failure));
  $("scene-message").hidden = !state.failure && (list || Boolean(state.scene));
  $("scene-message").textContent = state.failure || "Đang tải mô hình 3D…";
  pressed($("list-view"), list);
  $("list-view").textContent = list ? "Mở sa bàn 3D" : "Danh sách";
  for (const id of buttons) $(id).disabled = !state.scene || list;
  $("idle-activity").disabled = !state.scene || list;
  state.scene?.setEnabled(active && !list);
  fitFrame();
}

async function ensureScene() {
  if (!state.data || state.workspace !== "scene" || state.scene || state.loading || state.wantsList || state.failure) return;
  state.loading = true;
  updateLayout();
  try {
    const module = await import("./scene.js");
    if (state.wantsList || state.workspace !== "scene") return;
    const scene = new module.OfficeScene($("canvas-slot"), state.data.agents, {
      labels: placeLabels, select: choose, deliveries: showDeliveries,
      error: setSceneError, reset: resetCamera,
      camera: (camera) => remember({camera}),
    });
    state.scene = scene;
    scene.setReduced(stopAnimatedEffects());
    scene.setIdleActivity(idleActivity());
    if (preferences.camera) scene.restoreCamera(preferences.camera);
    else if (state.view !== "all") scene.focus(state.view);
    scene.select(state.selection);
    scene.update(state.data, state.deliveryInbox, true);
    state.deliveryInbox = [];
  } catch (error) {
    const message = error.constructor.name === "WebGLUnavailable"
      ? "Trình duyệt chưa hỗ trợ WebGL 2. Bạn vẫn có thể theo dõi qua danh sách agent."
      : "Không tải được sa bàn 3D. Bạn vẫn có thể theo dõi qua danh sách agent.";
    console.warn("Văn phòng 3D:", error);
    setSceneError(message);
  } finally {
    state.loading = false;
    updateLayout();
  }
}

const overlaps = (x, y, w, h, box) => x < box.x + box.w + 4 && x + w + 4 > box.x
  && y < box.y + box.h + 4 && y + h + 4 > box.y;
const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
const labelSizes = new Map();

function placeLabels(markers, width, height) {
  const badge = $("scene-deliveries");
  const occupied = badge.hidden ? [] : [{x: badge.offsetLeft, y: badge.offsetTop, w: badge.offsetWidth, h: badge.offsetHeight}];
  const priority = (id) => id === state.selection.agent ? 2 : workStates.has(agentById(id)?.status) ? 1 : 0;
  const prioritized = [...markers].sort(([id], [other]) => priority(other) - priority(id));
  const limit = height - 45;
  for (const [id, point] of prioritized) {
    const b = deskLabels.get(id);
    if (Math.abs(point.x) > 1.06 || Math.abs(point.y) > 1.06 || Math.abs(point.z) > 1) {
      b.hidden = true;
      continue;
    }
    if (b.hidden) b.hidden = false;
    if (!labelSizes.has(id)) labelSizes.set(id, [b.offsetWidth, b.offsetHeight]);
    const [w, h] = labelSizes.get(id);
    const idealX = (point.x + 1) * width * .5 - w * .5;
    const idealY = (1 - point.y) * height * .5 - h - 4;
    const candidates = [[0, 0], [0, -h - 5], [0, h + 5], [w * .65, 0], [-w * .65, 0],
      [0, -2 * h - 10], [w * .75, -h - 5], [-w * .75, -h - 5], [0, 2 * h + 10]];
    // Mở rộng vùng thử quanh hình chiếu và dùng danh sách cho nhãn hết chỗ.
    for (const dy of [-3, 3, -4, 4]) {
      for (const dx of [0, -1, 1, -2, 2]) candidates.push([dx * w * .72, dy * (h + 5)]);
    }
    const options = candidates.map(([dx, dy]) => ({x: clamp(idealX + dx, 5, width - w - 5),
      y: clamp(idealY + dy, 5, limit - h), w, h}));
    const spot = options.find((p) => !occupied.some((box) => overlaps(p.x, p.y, w, h, box)));
    if (!spot) {
      b.hidden = true;
      continue;
    }
    occupied.push(spot);
    b.style.transform = "translate(" + Math.round(spot.x) + "px," + Math.round(spot.y) + "px)";
  }
}

function present(data, reset = false) {
  state.data = data;
  if (!roomButtons.size) {
    if (!state.selection.agent && !state.selection.room) state.selection = {agent: data.run.current || data.agents[0].id};
    buildNavigation();
  }
  const id = state.mode + ":" + (data.run.id || "");
  reset ||= id !== state.visit;
  state.visit = id;
  const latest = data.transfers.at(-1);
  const fresh = reset ? [] : data.transfers.filter((event) => !event.pending
    && (event.id > state.cursor || state.pendingIds.has(event.id)));
  state.cursor = Math.max(reset ? 0 : state.cursor, latest?.id || 0);
  state.pendingIds = new Set(data.transfers.filter((event) => event.pending).map((event) => event.id));
  if (reset) state.deliveryInbox = [];
  if (state.mode === "demo") {
    statusBadge($("run-status"), "demo", "Không gọi API");
  } else {
    statusBadge($("run-status"), data.run.status, data.run.status === "done" ? "Hoàn thành" : undefined);
  }
  $("frame-run").hidden = state.mode === "live" && Boolean(data.run.id);
  const displayRounds = Number.isInteger(data.run.iteration) && Number.isInteger(data.run.max_iterations);
  $("run-rounds").hidden = !displayRounds;
  $("run-rounds").textContent = displayRounds
    ? "Vòng sửa " + data.run.iteration + " / " + data.run.max_iterations : "";
  $("demo-play").hidden = state.mode !== "demo";
  pressed($("demo-mode"), state.mode === "demo");
  pressed($("live-mode"), state.mode === "live");
  syncMotionControls();
  renderWorkspace();
  updateNavigation();
  renderInspector(reset);
  renderQuality();
  transferLabel(latest);
  if ($("handoffs").open) renderHandoffs();
  if (state.scene) {
    state.scene.setReduced(stopAnimatedEffects());
    state.scene.update(data, fresh, reset);
  } else if (!stopAnimatedEffects() && !state.failure) {
    state.deliveryInbox.push(...fresh);
  }
  ensureScene();
}

// Kịch bản chỉ chạy cục bộ, dùng cùng lớp hiển thị và tách khỏi luồng Python.
const script = [
  ["project_manager", "Mở lượt minh họa và giao tiếp nhận yêu cầu."],
  ["requirements_analyst", "Minh họa brief được chuyển cho Kiến trúc sư ý tưởng."],
  ["concept_architect", "Minh họa bàn giao định hướng cho Thiết kế công năng."],
  ["architect", "Minh họa chuyển chương trình công năng sang bàn kỹ thuật."],
  ["drafter", "Minh họa gửi bộ bản vẽ sơ bộ sang tư vấn phong thủy."],
  ["fengshui_advisor", "Minh họa chuyển gợi ý bố trí sang bước kiểm định."],
  ["reviewer", "Tình huống mô phỏng: đề nghị rà soát bố trí mặt bằng.", true],
  ["project_manager", "Điều phối phản hồi về bàn Thiết kế công năng.", true],
  ["architect", "Gửi phương án minh họa đã điều chỉnh để vẽ lại."],
  ["drafter", "Bàn giao bản vẽ minh họa đã cập nhật."],
  ["fengshui_advisor", "Minh họa chuyển gợi ý bố trí sang bước kiểm định."],
  ["reviewer", "Kết thúc thẩm định, chuyển hồ sơ sang dự toán."],
  ["cost_estimator", "Minh họa gửi dự toán để tổng hợp."],
  ["project_manager", "Minh họa chuyển hồ sơ sang bước kiểm tra cuối."],
  ["final_reviewer", "Kết thúc mô phỏng. Gói hồ sơ đến bàn trưng bày."],
];

let demo;
let demoTimer;

function demoButton() {
  $("demo-play").textContent = demo.index >= script.length ? "Chạy lại mô phỏng"
    : demo.playing ? "Tạm dừng mô phỏng" : "Tiếp tục mô phỏng";
}

function startDemo() {
  const agents = state.live.agents.map(({id, room, name, short, color, task}) => ({
    id, room, name, short, color, task, input: {}, output: {}, issues: [], runs: 0,
    version: null, summary: "", status: id === script[0][0] ? "running" : "waiting",
  }));
  demo = {index: 0, playing: true, data: {rooms: state.live.rooms, agents, transfers: [], geometry: null,
    cost_amounts: [], run: {id: "simulation", status: "running", current: script[0][0], fengshui_enabled: true,
      iteration: 0, max_iterations: 3}}};
  demoButton();
  present(demo.data, true);
  planDemo();
}

function planDemo() {
  clearTimeout(demoTimer);
  if (state.mode === "demo" && demo.playing && !document.hidden) demoTimer = setTimeout(advanceDemo, 1500);
}

function advanceDemo() {
  const [from, summary, feedback = false] = script[demo.index];
  const to = script[demo.index + 1]?.[0] || "showcase";
  const data = demo.data;
  const sender = data.agents.find((item) => item.id === from);
  const receiver = data.agents.find((item) => item.id === to);
  sender.status = feedback ? "feedback" : "done";
  sender.summary = summary;
  sender.runs += 1;
  sender.version = sender.runs;
  sender.output = {che_do: "Mô phỏng", su_kien: summary};
  if (feedback) sender.issues = [summary];
  else sender.issues = [];
  if (receiver) {
    receiver.status = receiver.runs && data.run.iteration && to !== "project_manager" ? "revising" : "running";
    receiver.input = {che_do: "Mô phỏng", tu_agent: sender.name};
  }
  if (from === "project_manager" && feedback) data.run.iteration += 1;
  data.run.current = receiver?.id || null;
  data.transfers.push({id: demo.index + 1, from, to, feedback, summary});
  demo.index += 1;
  if (demo.index === script.length) {
    demo.playing = false;
    data.run.status = "done";
  }
  demoButton();
  present(data);
  planDemo();
}

function changeMode(mode) {
  if (state.mode === mode || !state.live) return;
  clearTimeout(demoTimer);
  state.mode = mode;
  if (mode === "demo") startDemo();
  else present(state.live, true);
}

$("demo-mode").addEventListener("click", () => changeMode("demo"));
$("live-mode").addEventListener("click", () => changeMode("live"));
$("demo-play").addEventListener("click", () => {
  if (demo.index === script.length) startDemo();
  else {
    demo.playing = !demo.playing;
    demoButton();
    state.scene?.setReduced(stopAnimatedEffects());
    planDemo();
  }
});
document.addEventListener("visibilitychange", () => {
  if (state.mode === "demo") planDemo();
});

$("list-view").addEventListener("click", () => {
  state.wantsList = !(state.wantsList || state.failure);
  state.failure = "";
  remember({list: state.wantsList});
  updateLayout();
  ensureScene();
});
$("motion").addEventListener("click", () => {
  remember({motion: !reducedMotion()});
  syncMotionControls();
  state.scene?.setReduced(stopAnimatedEffects());
});
$("idle-activity").addEventListener("click", () => {
  remember({idleActivity: !idleActivity()});
  syncMotionControls();
  state.scene?.setIdleActivity(idleActivity());
});
motionQuery.addEventListener("change", () => {
  syncMotionControls();
  state.scene?.setReduced(stopAnimatedEffects());
});
$("reset").addEventListener("click", resetCamera);
$("enlarge").addEventListener("click", () => {
  state.enlarged = !state.enlarged;
  $("office").classList.toggle("enlarged", state.enlarged);
  pressed($("enlarge"), state.enlarged);
  $("enlarge").textContent = state.enlarged ? "Thu nhỏ cảnh" : "Mở rộng cảnh";
});
$("panel-toggle").addEventListener("click", () => togglePanel(!state.panelCollapsed));
$("handoff-filter").addEventListener("change", renderHandoffs);
$("handoffs").addEventListener("toggle", () => {
  $("handoff-action").textContent = $("handoffs").open ? "Thu gọn nhật ký" : "Mở nhật ký";
  if ($("handoffs").open && state.data) renderHandoffs();
});
$("quality-details").addEventListener("toggle", () => {
  $("quality-action").textContent = $("quality-details").open ? "Thu gọn" : "Xem chi tiết";
});
for (const [index, view] of views.entries()) {
  const button = $("tab-" + view);
  button.addEventListener("click", () => showWorkspace(view));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const next = views[(index + (event.key === "ArrowRight" ? 1 : views.length - 1)) % views.length];
    showWorkspace(next);
    $("tab-" + next).focus();
  });
}
$("zoom-in").addEventListener("click", () => state.scene?.zoom(1.18));
$("zoom-out").addEventListener("click", () => state.scene?.zoom(1 / 1.18));
$("project-model").addEventListener("click", () => focusRoom("showcase"));

window.addEventListener("message", ({data, source, origin}) => {
  if (source !== window.parent || origin !== window.location.origin || data?.type !== "streamlit:render") return;
  const payload = data.args?.data;
  if (!payload?.agents?.length) return;
  state.live = payload;
  const mode = data.args.mode;
  const managed = mode === "live" || mode === "demo";
  state.managed = managed;
  $("scene-mode").hidden = managed;
  if (managed && state.mode !== mode) changeMode(mode);
  else if (state.mode === "live") present(payload);
  updateLayout();
});

window.addEventListener("pagehide", () => {
  clearTimeout(demoTimer);
  state.scene?.dispose();
});
postStreamlit("streamlit:componentReady", {apiVersion: 1});
showWorkspace(state.workspace);
togglePanel(state.panelCollapsed);
fitFrame();
