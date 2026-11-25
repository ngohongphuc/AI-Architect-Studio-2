import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { buildOffice, rooms, visitPoints } from "./model.js";
import { WalkMap } from "./navigation.mjs";
import { deliveryStops, OfficeActors } from "./actors.mjs";

const HOME = new THREE.Vector3(18.5, 23.5, 28.2);
const ACTIVE = new Set(["running", "revising"]);
const ATTENTION = {
  error: "#ba3936", feedback: "#bd7029", awaiting_approval: "#c79022", needs_input: "#c79022",
};

export class WebGLUnavailable extends Error {}

export class OfficeScene {
  constructor(slot, agents, callbacks) {
    this.slot = slot;
    this.callbacks = callbacks;
    this.roomByAgent = new Map(agents.map((agent) => [agent.id, agent.room]));
    this.working = new Set();
    this.selection = {};
    this.frame = 0;
    this.enabled = true;
    this.intersecting = true;
    this.reduced = false;
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-12, 12, 9, -9, .1, 130);
    this.camera.position.copy(HOME);
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2", {alpha: true, antialias: true, powerPreference: "low-power"});
    if (!context) throw new WebGLUnavailable("WebGL 2 chưa sẵn sàng.");
    this.renderer = new THREE.WebGLRenderer({canvas, context, alpha: true, antialias: true});
    this.renderer.setPixelRatio(Math.min(1.45, window.devicePixelRatio || 1));
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.18;
    slot.append(canvas);

    const ambient = new THREE.HemisphereLight("#fff3d8", "#809b8d", 2.05);
    const key = new THREE.DirectionalLight("#ffe3bc", 2.45);
    key.position.set(-8, 15, 7);
    const fill = new THREE.DirectionalLight("#e6faf8", .77);
    fill.position.set(8, 8, -13);
    this.scene.add(ambient, key, fill);
    this.model = buildOffice(this.scene, agents);
    this.navigation = new WalkMap(this.model.footprints);
    this.actors = new OfficeActors(this.navigation, agents.map((agent) => {
      const home = this.model.figures.get(agent.id).home;
      const room = rooms[agent.room];
      const stops = deliveryStops(home, ([x, z]) => Math.abs(x - room.center[0]) <= room.width / 2
        && Math.abs(z - room.center[1]) <= room.depth / 2);
      return {...agent, home, stops};
    }), visitPoints, {drop: visitPoints.find(({id}) => id === "showcase-front")});
    this.folders = new Map();
    this.spareFolders = [];

    this.outline = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({
      color: "#0c7168", depthTest: false, transparent: true, opacity: .83,
    }));
    this.outline.visible = false;
    this.outline.renderOrder = 3;
    this.scene.add(this.outline);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, .34, 0);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = .14;
    this.controls.rotateSpeed = .63;
    this.controls.enablePan = true;
    this.controls.minPolarAngle = .27;
    this.controls.maxPolarAngle = 1.22;
    this.controls.minZoom = .69;
    this.controls.maxZoom = 3.7;
    this.controls.update();
    this.controls.addEventListener("change", () => this.invalidate());
    this.controls.addEventListener("start", () => { this.cameraTween = null; });
    this.controls.addEventListener("end", () => this.storeCamera());

    this.events = new AbortController();
    const {signal} = this.events;
    let pointer;
    canvas.addEventListener("pointerdown", (e) => {
      pointer = e.isPrimary && e.button === 0 ? {x: e.clientX, y: e.clientY} : null;
    }, {signal});
    canvas.addEventListener("pointerup", (e) => {
      if (pointer && Math.hypot(pointer.x - e.clientX, pointer.y - e.clientY) < 5) this.pick(e);
      pointer = null;
    }, {signal});
    canvas.addEventListener("pointercancel", () => { pointer = null; }, {signal});
    canvas.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      this.setEnabled(false);
      callbacks.error("Kết nối WebGL đã gián đoạn. Có thể tiếp tục bằng danh sách agent.");
    }, {signal});
    slot.addEventListener("keydown", (event) => this.onKey(event), {signal});
    document.addEventListener("visibilitychange", () => this.onVisibility(), {signal});
    this.sizeObserver = new ResizeObserver(() => this.resize());
    this.sizeObserver.observe(slot);
    this.visibilityObserver = new IntersectionObserver(([entry]) => {
      this.intersecting = entry.isIntersecting;
      this.onVisibility();
    });
    this.visibilityObserver.observe(slot);
    this.resize();
  }

  get visible() {
    return this.enabled && this.intersecting && !document.hidden;
  }

  setEnabled(enabled) {
    if (enabled === this.enabled) return;
    this.enabled = enabled;
    this.onVisibility();
    if (enabled) this.resize();
  }

  onVisibility() {
    this.actorFrame = null;
    clearTimeout(this.actorWake);
    if (this.visible) {
      this.invalidate();
    } else {
      cancelAnimationFrame(this.frame);
      this.frame = 0;
    }
  }

  setReduced(reduced) {
    if (this.reduced === reduced) return;
    this.reduced = reduced;
    this.actorFrame = null;
    clearTimeout(this.actorWake);
    this.controls.enableDamping = !reduced;
    if (reduced) {
      if (this.cameraTween) this.finishCamera(this.cameraTween);
    }
    this.invalidate();
  }

  setIdleActivity(enabled) {
    this.actors.setIdle(enabled);
    this.invalidate();
  }

  resize() {
    const width = this.slot.clientWidth, height = this.slot.clientHeight;
    if (!width || !height) return;
    if (width !== this.width || height !== this.height) {
      this.width = width;
      this.height = height;
      this.renderer.setSize(width, height, false);
      const aspect = width / height;
      const half = Math.max(8.16, 12.6 / aspect);
      this.camera.left = -half * aspect;
      this.camera.right = half * aspect;
      this.camera.top = half;
      this.camera.bottom = -half;
      this.camera.updateProjectionMatrix();
    }
    this.invalidate();
  }

  invalidate() {
    if (this.visible && !this.frame) this.frame = requestAnimationFrame((t) => this.draw(t));
  }

  update(data, fresh, reset) {
    if (reset) this.actors.resetDeliveries();
    const statusesChanged = this.actors.updateStatuses(data.agents);
    const modelChanged = this.model.updateHouse(data.geometry);
    const boardsChanged = this.model.updateScreens(data);
    const working = new Set(data.agents.filter((agent) => ACTIVE.has(agent.status)).map((agent) => agent.id));
    const workChanged = this.working.size !== working.size || [...working].some((id) => !this.working.has(id));
    if (workChanged) this.working = working;
    if (workChanged || statusesChanged) this.updateFigures();
    const queued = !this.reduced && this.actors.enqueue(fresh);
    if (reset || modelChanged || boardsChanged || statusesChanged || workChanged || queued) this.invalidate();
  }

  updateFigures() {
    for (const [id, figure] of this.model.figures) {
      const working = this.working.has(id);
      const selected = this.selection.agent === id;
      const attention = ATTENTION[this.actors.agents.get(id).status];
      figure.luminaire.hood.emissiveIntensity = working ? 1.3 : .05;
      figure.luminaire.lit.opacity = working ? .68 : .04;
      figure.ring.scale.set(working || selected ? .82 : .61, 1, working || selected ? .82 : .61);
      figure.ringMat.opacity = working || selected ? 1 : .67;
      figure.signal.visible = Boolean(attention);
      if (attention) figure.signal.material.color.set(attention);
    }
  }

  select(selection) {
    this.selection = selection;
    this.updateFigures();
    const r = rooms[selection.room || this.roomByAgent.get(selection.agent)];
    this.outline.visible = Boolean(r);
    if (r) {
      const [x, z] = r.center;
      const w = r.width * .51, d = r.depth * .51;
      this.outline.geometry.dispose();
      this.outline.geometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(x - w, .057, z - d), new THREE.Vector3(x + w, .057, z - d),
        new THREE.Vector3(x + w, .057, z + d), new THREE.Vector3(x - w, .057, z + d),
      ]);
    }
    this.invalidate();
  }

  focus(room) {
    const record = rooms[room];
    const target = record ? new THREE.Vector3(record.center[0], .38, record.center[1]) : new THREE.Vector3(0, .34, 0);
    const zoom = record ? (room === "showcase" ? 2.76 : 2.33) : 1;
    const focus = {target, position: HOME.clone().add(target), zoom};
    if (this.reduced || !this.visible) {
      this.finishCamera(focus);
    } else {
      this.cameraTween = {...focus, started: performance.now(), from: this.camera.position.clone(),
        fromTarget: this.controls.target.clone(), fromZoom: this.camera.zoom};
      this.invalidate();
    }
  }

  finishCamera(focus) {
    this.cameraTween = null;
    this.camera.position.copy(focus.position);
    this.camera.zoom = focus.zoom;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(focus.target);
    this.controls.update();
    this.storeCamera();
    this.invalidate();
  }

  restoreCamera(saved) {
    if (!saved || !Array.isArray(saved.position) || !Array.isArray(saved.target)) return;
    const values = [...saved.position, ...saved.target, saved.zoom];
    if (values.length !== 7 || !values.every(Number.isFinite) || saved.zoom < .69 || saved.zoom > 3.7) return;
    this.finishCamera({position: new THREE.Vector3(...saved.position),
      target: new THREE.Vector3(...saved.target), zoom: saved.zoom});
  }

  storeCamera() {
    this.callbacks.camera({
      position: this.camera.position.toArray(), target: this.controls.target.toArray(),
      zoom: this.camera.zoom,
    });
  }

  zoom(factor) {
    this.cameraTween = null;
    this.camera.zoom = THREE.MathUtils.clamp(this.camera.zoom * factor, this.controls.minZoom, this.controls.maxZoom);
    this.camera.updateProjectionMatrix();
    this.storeCamera();
    this.invalidate();
  }

  onKey(event) {
    const key = event.key;
    if (key === "+" || key === "=") this.zoom(1.18);
    else if (key === "-") this.zoom(1 / 1.18);
    else if (key === "Home") this.callbacks.reset();
    else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(key)) {
      this.cameraTween = null;
      const offset = this.camera.position.clone().sub(this.controls.target);
      const spherical = new THREE.Spherical().setFromVector3(offset);
      if (key === "ArrowLeft" || key === "ArrowRight") spherical.theta += key === "ArrowLeft" ? -.15 : .15;
      else spherical.phi = THREE.MathUtils.clamp(spherical.phi + (key === "ArrowUp" ? -.11 : .11), .27, 1.22);
      this.camera.position.setFromSpherical(spherical).add(this.controls.target);
      this.controls.update();
      this.storeCamera();
      this.invalidate();
    } else return;
    event.preventDefault();
  }

  pick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const point = new THREE.Vector2((event.clientX - rect.x) / rect.width * 2 - 1,
      1 - (event.clientY - rect.y) / rect.height * 2);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(point, this.camera);
    const hit = ray.intersectObjects(this.model.picks, false)[0]?.object.userData;
    if (hit?.agentId) this.callbacks.select({agent: hit.agentId});
    else if (hit?.roomId) this.callbacks.select({room: hit.roomId});
  }

  drawFolders() {
    const jobs = this.actors.handoffs;
    for (const [id, folder] of this.folders) {
      if (jobs.get(id)?.owner) continue;
      folder.mesh.visible = false;
      this.scene.add(folder.mesh);
      this.folders.delete(id);
      this.spareFolders.push(folder);
    }
    const k = this.model.k;
    for (const {event, owner, sender} of jobs.values()) {
      if (!owner) continue;
      const grip = this.model.figures.get(owner.id).grips.get(owner === sender ? "right" : "left");
      let folder = this.folders.get(event.id);
      if (!folder) {
        folder = this.spareFolders.pop();
        if (!folder) {
          const mesh = new THREE.Group();
          k.tile(mesh, "#fff0cf", 0, .017, .071, .30, .048, .245);
          const cover = k.box(mesh, "#138575", 0, .049, .071, .31, .018, .25);
          k.box(mesh, "#fff8e4", -.082, .06, .095, .075, .006, .083);
          folder = {mesh, cover};
        }
        folder.cover.material = k.material(event.feedback ? "#be621b" : "#138575");
        folder.mesh.visible = true;
        folder.mesh.position.set(0, 0, 0);
        folder.mesh.rotation.set(0, 0, 0);
        folder.settle = null;
        grip.add(folder.mesh);
        this.folders.set(event.id, folder);
      } else if (folder.mesh.parent !== grip) {
        // Giữ nguyên vị trí giữa hai bàn tay tại đúng thời điểm đổi chủ.
        grip.attach(folder.mesh);
        folder.settle = {start: this.actors.time, position: folder.mesh.position.clone(),
          rotation: folder.mesh.quaternion.clone()};
      }
      if (folder.settle) {
        const t = Math.min(1, (this.actors.time - folder.settle.start) / .18);
        folder.mesh.position.copy(folder.settle.position).multiplyScalar(1 - t);
        folder.mesh.quaternion.identity().slerp(folder.settle.rotation, 1 - t);
        if (t === 1) folder.settle = null;
      }
    }
  }

  drawActors(time) {
    if (!this.reduced) this.actors.advance(this.actorFrame == null ? 0 : (time - this.actorFrame) / 1000);
    this.actorFrame = time;
    for (const [id, figure] of this.model.figures) {
      const pose = this.actors.agents.get(id);
      const swing = Math.sin(pose.phase) * pose.stride * (1 - pose.sitting);
      const delivery = pose.handoff;
      const sender = delivery?.sender === pose;
      const exchange = delivery?.phase === "exchanging";
      const elapsed = exchange ? this.actors.time - delivery.started : 0;
      const reach = exchange ? Math.max(0, Math.min(1, (elapsed - .12) / .38,
        (delivery.exchangeUntil - this.actors.time) / .23)) : 0;
      const work = !this.reduced && pose.atHome && !exchange && this.working.has(id);
      figure.group.position.set(pose.position[0], 0, pose.position[1]);
      figure.group.rotation.y = pose.angle;
      figure.body.position.y = -.025 * pose.sitting + Math.abs(swing) * .06
        + (work ? Math.sin(time / 258 + figure.phase) * .015 : 0);
      figure.body.position.z = reach * .067;
      figure.right.rotation.x = work ? Math.sin(time / 216 + figure.phase) * .21 - .55
        : -.34 * swing - .40 * pose.sitting;
      figure.left.rotation.x = .34 * swing - .40 * pose.sitting;
      if (sender && delivery.owner === pose && !exchange) figure.right.rotation.x = -.96 - .1 * swing;
      if (exchange) {
        const arm = sender ? figure.right : figure.left;
        const neutral = sender && delivery.owner === pose ? -.96 : !sender && delivery.owner === pose ? -.62 : -.14;
        arm.rotation.x = THREE.MathUtils.lerp(neutral, -1.48, reach);
      }
      for (const [i, leg] of figure.legs.entries()) {
        leg.hip.rotation.x = -1.44 * pose.sitting + (i ? swing : -swing) * .47;
        leg.knee.rotation.x = 1.37 * pose.sitting + Math.max(0, (i ? -swing : swing)) * .48;
      }
    }
  }

  draw(time) {
    this.frame = 0;
    if (!this.visible || !this.width) return;
    // Màn hình đứng yên không lên lịch frame. Chuyển động nền giới hạn khoảng 30 FPS.
    const motion = !this.reduced && (this.working.size || this.actors.moving);
    if (motion && !this.cameraTween && time - (this.lastFrame || 0) < 31) {
      this.invalidate();
      return;
    }
    this.lastFrame = time;
    if (this.cameraTween) {
      const focus = this.cameraTween;
      const t = Math.min(1, (time - focus.started) / 440);
      const ease = 1 - Math.pow(1 - Math.max(0, t), 3);
      this.camera.position.lerpVectors(focus.from, focus.position, ease);
      this.controls.target.lerpVectors(focus.fromTarget, focus.target, ease);
      this.camera.zoom = THREE.MathUtils.lerp(focus.fromZoom, focus.zoom, ease);
      this.camera.updateProjectionMatrix();
      if (t >= 1) this.finishCamera(focus);
    }
    const damping = this.controls.update();

    this.drawActors(time);
    this.drawFolders();
    this.callbacks.deliveries([...this.actors.handoffs.values()].filter(({phase}) => phase !== "returning")
      .map(({event, phase, owner, sender}) => ({event, phase: phase === "exchanging" && owner !== sender
        ? "received" : phase})));
    this.renderer.render(this.scene, this.camera);
    this.callbacks.labels([...this.model.figures].map(([id, figure]) => {
      const anchor = figure.group.position.clone();
      anchor.y = 1.19 + figure.body.position.y;
      return [id, anchor.project(this.camera)];
    }), this.width, this.height);
    clearTimeout(this.actorWake);
    if (motion || this.cameraTween || damping || (!this.reduced && this.actors.moving)) this.invalidate();
    else if (!this.reduced && Number.isFinite(this.actors.nextWake)) {
      this.actorWake = setTimeout(() => this.invalidate(), Math.max(32, this.actors.nextWake * 1000));
    }
  }

  dispose() {
    this.enabled = false;
    cancelAnimationFrame(this.frame);
    clearTimeout(this.actorWake);
    this.events.abort();
    this.sizeObserver.disconnect();
    this.visibilityObserver.disconnect();
    this.controls.dispose();
    const geometries = new Set(), materials = new Set();
    this.scene.traverse((obj) => {
      if (obj.geometry) geometries.add(obj.geometry);
      if (obj.material) materials.add(obj.material);
      if (obj.isInstancedMesh) obj.dispose();
    });
    for (const geometry of geometries) geometry.dispose();
    for (const material of materials) {
      material.map?.dispose();
      material.dispose();
    }
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
  }
}
