const at = (name) => document.getElementById(name);
const viewer = at("viewer"), viewport = at("viewport"), image = at("image"), sheet = at("sheet");
let zoom = 1, source, drag, lastHeight;

function post(type, payload = {}) {
  window.parent.postMessage({type, isStreamlitMessage: true, ...payload}, window.location.origin);
}

function resizeFrame() {
  const height = Math.ceil(viewer.getBoundingClientRect().height) + 4;
  if (height === lastHeight || document.fullscreenElement) return;
  lastHeight = height;
  post("streamlit:setFrameHeight", {height});
}

function layout(center = false) {
  if (!image.naturalWidth || sheet.hidden) return;
  const width = viewport.clientWidth;
  const height = viewport.clientHeight;
  const fit = Math.min(width / image.naturalWidth, height / image.naturalHeight, 1);
  const w = Math.max(1, Math.floor(image.naturalWidth * fit * zoom));
  const h = Math.max(1, Math.floor(image.naturalHeight * fit * zoom));
  image.style.width = w + "px";
  image.style.height = h + "px";
  sheet.style.width = Math.max(w, width) + "px";
  sheet.style.height = Math.max(h, height) + "px";
  if (center) viewport.scrollTo(Math.max(0, (w - width) / 2), Math.max(0, (h - height) / 2));
  viewport.classList.toggle("pannable", w > width || h > height);
  at("zoom").textContent = Math.round(zoom * 100) + "%";
  at("minus").disabled = zoom <= .5;
  at("plus").disabled = zoom >= 5;
}

function magnify(next) {
  zoom = Math.min(5, Math.max(.5, next));
  layout(true);
}

at("fit").addEventListener("click", () => magnify(1));
at("minus").addEventListener("click", () => magnify(zoom / 1.25));
at("plus").addEventListener("click", () => magnify(zoom * 1.25));
viewport.addEventListener("keydown", (event) => {
  if (event.key === "+" || event.key === "=") magnify(zoom * 1.25);
  else if (event.key === "-") magnify(zoom / 1.25);
  else if (event.key === "Home") magnify(1);
  else return;
  event.preventDefault();
});
viewport.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || event.pointerType === "touch" || !viewport.classList.contains("pannable")) return;
  drag = [event.clientX, event.clientY, viewport.scrollLeft, viewport.scrollTop];
  viewport.setPointerCapture(event.pointerId);
  viewport.classList.add("dragging");
});
viewport.addEventListener("pointermove", (event) => {
  if (drag) viewport.scrollTo(drag[2] + drag[0] - event.clientX, drag[3] + drag[1] - event.clientY);
});
viewport.addEventListener("lostpointercapture", () => {
  drag = null;
  viewport.classList.remove("dragging");
});

function expandLabel() {
  const expanded = document.fullscreenElement || viewer.classList.contains("is-expanded");
  at("expand-label").textContent = expanded ? "Thu lại" : document.fullscreenEnabled ? "Toàn màn hình" : "Mở rộng";
  at("expand").setAttribute("aria-pressed", String(Boolean(expanded)));
}

at("expand").addEventListener("click", async () => {
  if (document.fullscreenElement) {
    await document.exitFullscreen();
  } else if (!viewer.classList.contains("is-expanded") && document.fullscreenEnabled) {
    try { await viewer.requestFullscreen(); }
    catch { viewer.classList.add("is-expanded"); }
  } else {
    viewer.classList.toggle("is-expanded");
  }
  expandLabel();
  layout(true);
  resizeFrame();
});
document.addEventListener("fullscreenchange", () => {
  expandLabel();
  layout(true);
  resizeFrame();
});
image.addEventListener("load", () => {
  at("message").hidden = true;
  sheet.hidden = false;
  magnify(1);
  resizeFrame();
});
image.addEventListener("error", () => {
  at("message").textContent = "Không đọc được ảnh bản vẽ. Có thể thử tờ khác hoặc dùng tệp PDF nếu có.";
  at("message").hidden = false;
  sheet.hidden = true;
});
window.addEventListener("message", ({data, source: sender, origin}) => {
  if (sender !== window.parent || origin !== window.location.origin || data?.type !== "streamlit:render") return;
  const {source: url, title} = data.args;
  at("caption").textContent = image.alt = title;
  if (source !== url) {
    source = url;
    at("message").textContent = "Đang tải tờ bản vẽ…";
    at("message").hidden = false;
    sheet.hidden = true;
    image.src = url;
  }
});
new ResizeObserver(() => { layout(); resizeFrame(); }).observe(viewer);
expandLabel();
post("streamlit:componentReady", {apiVersion: 1});
resizeFrame();
