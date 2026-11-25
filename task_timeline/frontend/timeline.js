const $ = (id) => document.getElementById(id);
const markerStyles = {
  queued: ["○", "neutral"], canceled: ["⊘", "neutral"], handoff: ["→", "brand"],
  repair: ["↶", "warning"], retry: ["↻", "warning"], approval: ["◆", "warning"],
};
const phaseStyles = {
  success: ["✓", "Đã xử lý"], info: ["›", "Đang làm"],
  danger: ["!", "Lỗi"], neutral: ["×", "Hủy"],
};
const fullClock = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
});

let data, statuses, windowRange, scope, selected, syncedAt, live;
let lastHeight, lastWidth, timer;

function post(type, detail = {}) {
  window.parent.postMessage({isStreamlitMessage: true, type, ...detail}, window.location.origin);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function fitFrame() {
  const height = Math.ceil($("timeline").getBoundingClientRect().height) + 3;
  if (!height || height === lastHeight) return;
  lastHeight = height;
  post("streamlit:setFrameHeight", {height});
}

function setTone(element, tone) {
  for (const key of ["fg", "bg", "border"]) element.style.setProperty("--" + key, "var(--" + tone + "-" + key + ")");
}

function legend(marks) {
  const entries = [
    ...Object.entries(phaseStyles).map(([tone, [icon, label]]) => ({tone, icon, label})),
    {tone: "warning", icon: "", label: "Thời gian chờ duyệt", className: "approval"},
    ...Object.entries(markerStyles).map(([kind, [icon, tone]]) => ({tone, icon, label: marks[kind]})),
  ];
  $("legend").replaceChildren(...entries.map(({tone, icon, label, className}) => {
    const item = el("span");
    const badge = el("i", className, icon);
    badge.setAttribute("aria-hidden", "true");
    setTone(badge, tone);
    item.append(badge, document.createTextNode(label));
    return item;
  }));
}

function endAt(span, now) {
  return span[1] ?? Math.max(span[0], now);
}

function bounds(now) {
  const {start: first, end, live} = data.extent;
  const last = live ? Math.max(end, now) : end;
  const padding = first === last ? 500 : Math.max(1, (last - first) * .035);
  return [first - padding, last + padding];
}

function now() {
  return data.server_now + performance.now() - syncedAt;
}

function within(full, start, duration) {
  const left = Math.min(Math.max(start, full[0]), full[1] - duration);
  return [left, left + duration];
}

function arrange(items, gap) {
  const ends = [];
  const ordered = items.sort((a, b) => a.left - b.left || a.right - b.right);
  for (const item of ordered) {
    const available = ends.findIndex((end) => end + gap <= item.left);
    item.lane = available < 0 ? ends.length : available;
    ends[item.lane] = item.right;
  }
  return ends.length;
}

function row(name, isAxis = false) {
  const element = el("div", isAxis ? "row axis" : "row");
  if (!isAxis) {
    element.setAttribute("role", "group");
    element.setAttribute("aria-label", name);
  }
  const track = el("div", "track");
  element.append(el("div", "name", name), track);
  return {element, track};
}

function ticks(track, positions, clock, range) {
  const duration = range[1] - range[0];
  for (const part of positions) {
    const tick = el("div", "tick");
    tick.style.left = (part * 100) + "%";
    if (clock) tick.append(el("span", "", clock.format(range[0] + part * duration)));
    track.append(tick);
  }
}

function chartButton(id, focusKey, className, tone, description, text) {
  const button = el("button", className);
  button.type = "button";
  button.dataset.focus = focusKey;
  button.dataset.selection = id;
  button.setAttribute("aria-label", description);
  button.setAttribute("aria-pressed", String(id === selected));
  button.title = description;
  const label = el("span", "", text);
  label.setAttribute("aria-hidden", "true");
  button.append(label);
  setTone(button, tone);
  button.addEventListener("click", () => {
    if (id === selected) return;
    selected = id;
    for (const item of $("plot").querySelectorAll("[data-selection]")) {
      item.setAttribute("aria-pressed", String(item.dataset.selection === id));
    }
    post("streamlit:setComponentValue", {value: {id, scope}, dataType: "json"});
  });
  return button;
}

function attemptButton(item, type, span, left, right, top, width) {
  const waiting = type === "approval";
  const tone = waiting ? "warning" : item.tone;
  const [icon, phase] = waiting ? ["◆", "Chờ duyệt"] : phaseStyles[tone];
  const status = statuses[item.status];
  const timing = fullClock.format(span[0]) + (span[1] === null ? " → hiện tại" : " → " + fullClock.format(span[1]));
  const description = [item.name, "Lần " + item.number, status, phase !== status ? phase : "", timing]
    .filter(Boolean).join(" · ");
  const point = right - left < 2;
  const skin = (point ? "point" : "segment") + (waiting ? " approval" : "") + (span[1] === null ? " live-end" : "");
  const button = chartButton(item.id, item.id + ":" + type, skin, tone, description,
    point ? icon : icon + " Lần " + item.number);
  button.style.left = (left / width * 100) + "%";
  button.style.top = top + "px";
  if (!point) button.style.width = ((right - left) / width * 100) + "%";
  return button;
}

function draw() {
  if (!data || !$("plot").offsetWidth) return;
  const plot = $("plot");
  const focused = document.activeElement?.dataset.focus;
  const instant = now();
  const full = bounds(instant);
  if (windowRange) {
    const duration = windowRange[1] - windowRange[0];
    windowRange = duration >= full[1] - full[0] ? null : within(full, windowRange[0], duration);
  }
  const range = windowRange || full;
  const length = range[1] - range[0];
  const axis = row("Agent", true);
  plot.replaceChildren(axis.element);
  const width = axis.track.clientWidth;
  if (!width) return;
  const divisions = width < 520 ? 3 : 5;
  const positions = Array.from({length: divisions + 1}, (_, index) => index / divisions);
  const clockOptions = {hour: "2-digit", minute: "2-digit", second: "2-digit"};
  if (length < 5000) clockOptions.fractionalSecondDigits = length < 50 ? 3 : 2;
  if (length > 3600000) delete clockOptions.second;
  if (length > 43200000) Object.assign(clockOptions, {day: "2-digit", month: "2-digit"});
  ticks(axis.track, positions, new Intl.DateTimeFormat("vi-VN", clockOptions), range);
  const x = (at) => (at - range[0]) / length * width;
  const visible = (left, right) => left <= width && right >= 0;
  const clip = (value) => Math.max(0, Math.min(value, width));

  for (const agent of data.rows) {
    const laneRow = row(agent.name);
    ticks(laneRow.track, positions, null, range);
    const markers = data.markers.filter((item) => item.agent === agent.id && visible(x(item.at), x(item.at)))
      .map((item) => ({item, left: x(item.at) - 9, right: x(item.at) + 9}));
    const markLanes = arrange(markers, 3);
    const attempts = [];
    for (const item of data.attempts) {
      if (item.agent !== agent.id) continue;
      const periods = Object.entries({processing: item.processing, approval: item.approval})
        .filter(([, span]) => span && visible(x(span[0]), x(endAt(span, instant))))
        .map(([type, span]) => ({type, span, left: clip(x(span[0])), right: clip(x(endAt(span, instant)))}));
      if (!periods.length) continue;
      attempts.push({item, periods, left: Math.min(...periods.map((part) => part.left)),
        right: Math.max(...periods.map((part) => Math.max(part.right, part.left + 5)))});
    }
    const attemptLanes = arrange(attempts, 4);
    laneRow.track.style.minHeight = Math.max(34, 10 + markLanes * 22 + attemptLanes * 24) + "px";
    for (const {item, lane} of markers) {
      const [icon, tone] = markerStyles[item.kind];
      const title = item.label + " · " + fullClock.format(item.at) + (item.detail ? " · " + item.detail : "");
      const button = chartButton(item.id, item.id, "marker", tone, title, icon);
      button.style.left = ((x(item.at) / width) * 100) + "%";
      button.style.top = (5 + lane * 22) + "px";
      laneRow.track.append(button);
    }
    for (const {item, periods, lane} of attempts) {
      for (const {type, span, left, right} of periods) {
        laneRow.track.append(attemptButton(item, type, span, left, right, 5 + markLanes * 22 + lane * 24, width));
      }
    }
    plot.append(laneRow.element);
  }
  if (focused) plot.querySelector('[data-focus="' + CSS.escape(focused) + '"]')?.focus({preventScroll: true});
  $("range-label").textContent = fullClock.format(range[0]) + " – " + fullClock.format(range[1])
    + (live ? " · Đang cập nhật" : "");
  $("zoom-out").disabled = $("reset").disabled = !windowRange;
  $("zoom-in").disabled = length <= 2;
  $("pan-box").hidden = !windowRange;
  if (windowRange) {
    const available = full[1] - full[0] - length;
    if (document.activeElement !== $("pan")) $("pan").value = String(1000 * (range[0] - full[0]) / Math.max(available, 1));
    $("pan").setAttribute("aria-valuetext", fullClock.format(range[0]) + " – " + fullClock.format(range[1]));
  }
  fitFrame();
}

function zoom(factor) {
  if (!data) return;
  const full = bounds(now());
  const [left, right] = windowRange || full;
  const duration = Math.max(2, (right - left) * factor);
  windowRange = duration >= full[1] - full[0] ? null : within(full, (left + right - duration) / 2, duration);
  draw();
}

$("zoom-in").addEventListener("click", () => zoom(.5));
$("zoom-out").addEventListener("click", () => zoom(2));
$("reset").addEventListener("click", () => { windowRange = null; draw(); });
$("pan").addEventListener("input", () => {
  if (!windowRange) return;
  const full = bounds(now());
  const duration = windowRange[1] - windowRange[0];
  windowRange = within(full, full[0] + (full[1] - full[0] - duration) * Number($("pan").value) / 1000, duration);
  draw();
});

new ResizeObserver(() => {
  const width = $("timeline").clientWidth;
  if (width === lastWidth) return;
  lastWidth = width;
  draw();
  fitFrame();
}).observe($("timeline"));

window.addEventListener("message", ({data: message, source, origin}) => {
  if (source !== window.parent || origin !== window.location.origin || message?.type !== "streamlit:render") return;
  const args = message.args;
  if (scope !== args.data.scope) {
    scope = args.data.scope;
    windowRange = selected = null;
  }
  data = args.data;
  statuses = args.statuses;
  syncedAt = performance.now();
  for (const [tone, values] of Object.entries(args.tones)) {
    ["fg", "bg", "border"].forEach((key, i) => $("timeline").style.setProperty("--" + tone + "-" + key, values[i]));
  }
  legend(args.marks);
  live = data.extent.live;
  clearInterval(timer);
  if (live) timer = setInterval(() => { if (!document.hidden) draw(); }, 1000);
  draw();
});

window.addEventListener("pagehide", () => clearInterval(timer));
post("streamlit:componentReady", {apiVersion: 1});
fitFrame();
