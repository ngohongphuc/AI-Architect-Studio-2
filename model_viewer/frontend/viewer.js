import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { parseGlb } from "./glb.mjs";

const at = (id) => document.getElementById(id);
const stage = at("stage"), message = at("message"), cut = at("cut");
const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
let renderer, scene, camera, controls, model, bounds, source, lastHeight, queued = false;

function post(type, payload = {}) {
  window.parent.postMessage({type, isStreamlitMessage: true, ...payload}, window.location.origin);
}

function resizeFrame() {
  const height = Math.ceil(at("viewer").getBoundingClientRect().height) + 4;
  if (height !== lastHeight) post("streamlit:setFrameHeight", {height: lastHeight = height});
}

function draw() {
  if (queued || !renderer) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    renderer.render(scene, camera);
  });
}

function fail(text) {
  message.textContent = text;
  message.hidden = false;
}

function setup() {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("webgl2", {antialias: true, alpha: true});
  if (!context) return false;
  renderer = new THREE.WebGLRenderer({canvas, context, antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.localClippingEnabled = true;
  renderer.shadowMap.enabled = true;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, 1, .1, 400);
  controls = new OrbitControls(camera, canvas);
  controls.maxPolarAngle = Math.PI * .52;
  controls.addEventListener("change", draw);
  scene.add(new THREE.HemisphereLight("#ffffff", "#b9b2a4", 1.9));
  stage.append(canvas);
  return true;
}

function sunlight(size, center) {
  const sun = new THREE.DirectionalLight("#fff4e0", 2.1);
  sun.position.copy(center).add(new THREE.Vector3(.36, 1.05, .78).multiplyScalar(size));
  sun.target.position.copy(center);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.normalBias = .04;
  sun.shadow.bias = -.0004;
  Object.assign(sun.shadow.camera, {left: -size * .75, right: size * .75, top: size * .75, bottom: -size * .75, near: .1, far: size * 3});
  return [sun, sun.target];
}

function clear() {
  model?.traverse((item) => {
    item.geometry?.dispose();
    item.material?.dispose();
  });
  if (model) scene.remove(model);
}

function build(data) {
  clear();
  model = new THREE.Group();
  for (const part of data.parts) {
    const group = new THREE.Group();
    group.name = part.name;
    group.userData.group = part.group;
    for (const item of part.primitives) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(item.position, 3));
      geometry.setAttribute("normal", new THREE.BufferAttribute(item.normal, 3));
      geometry.setIndex(new THREE.BufferAttribute(item.index, 1));
      const pbr = item.material.pbrMetallicRoughness, [r, g, b, a] = pbr.baseColorFactor;
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(r, g, b), roughness: pbr.roughnessFactor, metalness: pbr.metallicFactor * .3,
        transparent: a < 1, opacity: a, depthWrite: a >= 1, side: THREE.DoubleSide, clippingPlanes: [clip], clipShadows: true,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = a >= 1;
      mesh.receiveShadow = a >= 1;
      group.add(mesh);
      if (a >= 1) {
        group.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry),
          new THREE.LineBasicMaterial({color: "#3b3f42", transparent: true, opacity: .16, clippingPlanes: [clip]})));
      }
    }
    model.add(group);
  }
  bounds = new THREE.Box3().setFromObject(model);
  const size = bounds.getSize(new THREE.Vector3()).length(), center = bounds.getCenter(new THREE.Vector3());
  model.add(...sunlight(size, center));
  scene.add(model);
  floorButtons(data);
  cut.value = 100;
  applyCut();
  look("axon");
}

function floorButtons(data) {
  at("floors").replaceChildren(...data.parts.map((part) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = part.name;
    button.setAttribute("aria-pressed", "true");
    button.addEventListener("click", () => {
      const group = model.children.find((item) => item.name === part.name);
      group.visible = !group.visible;
      button.setAttribute("aria-pressed", String(group.visible));
      draw();
    });
    return button;
  }));
}

function applyCut() {
  const whole = Number(cut.value) >= 100;
  const low = Math.max(0, bounds.min.y), level = low + (bounds.max.y - low) * Number(cut.value) / 100;
  clip.constant = whole ? 1e6 : level;
  at("cut-value").textContent = whole ? "Không cắt" : "+" + level.toFixed(2).replace(".", ",") + " m";
  draw();
}

const VIEWS = {street: [.42, .06, 1], axon: [.75, .62, .9], back: [-.6, .5, -1], top: [.001, 1, .02]};

function look(name) {
  const center = bounds.getCenter(new THREE.Vector3());
  const radius = bounds.getSize(new THREE.Vector3()).length() / 2;
  const half = Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * Math.min(1, camera.aspect));
  camera.position.copy(center).add(new THREE.Vector3(...VIEWS[name]).normalize().multiplyScalar(radius / Math.sin(half) * 1.04));
  controls.target.copy(center);
  controls.update();
  draw();
}

function resize() {
  if (!renderer) return;
  const width = stage.clientWidth, height = stage.clientHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / Math.max(1, height);
  camera.updateProjectionMatrix();
  draw();
}

for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => bounds && look(button.dataset.view));
}
cut.addEventListener("input", () => bounds && applyCut());
window.addEventListener("message", ({data, source: sender, origin}) => {
  if (sender !== window.parent || origin !== window.location.origin || data?.type !== "streamlit:render") return;
  if (source === data.args.glb) return;
  source = data.args.glb;
  if (!renderer && !setup()) {
    fail("Trình duyệt chưa hỗ trợ WebGL 2. Có thể tải tệp GLB để xem bằng phần mềm khác.");
    return;
  }
  try {
    resize();
    build(parseGlb(Uint8Array.from(atob(source), (c) => c.charCodeAt(0)).buffer));
    message.hidden = true;
  } catch (error) {
    fail("Không đọc được mô hình 3D. " + error.message);
  }
});
new ResizeObserver(() => { resize(); resizeFrame(); }).observe(at("viewer"));
post("streamlit:componentReady", {apiVersion: 1});
resizeFrame();
