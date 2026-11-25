import * as THREE from "three";

// Tọa độ theo mặt sàn X/Z, nhìn từ phía cửa kính và phần sàn mở.
export const rooms = {
  management: { center: [-6.40, -4.40], width: 5.4, depth: 3.5, door: [-6.40, -2.51] },
  reception:  { center: [-6.47, 1.68], width: 5.3, depth: 5.55, door: [-3.67, .62] },
  design:     { center: [0, -4.40], width: 6.55, depth: 3.5, door: [0, -2.51] },
  drawing:    { center: [6.48, -4.40], width: 5.4, depth: 3.5, door: [6.42, -2.51] },
  review:     { center: [6.53, .13], width: 5.25, depth: 3.30, door: [3.74, .90] },
  finance:    { center: [6.53, 4.57], width: 5.25, depth: 3.4, door: [3.74, 5.38] },
  archive:    { center: [-.02, 4.67], width: 5.93, depth: 3.2, door: [1.34, 2.99] },
  showcase:   { center: [-.07, .26], width: 3.2, depth: 2.35 },
  lounge:    { center: [-6.63, 5.60], width: 5.65, depth: 1.62 },
};

const desks = {
  project_manager:      { seat: [-6.34, -3.48], lamp: [-7.46, -4.14] },
  requirements_analyst: { seat: [-6.33, .69], lamp: [-7.64, -.10] },
  concept_architect:    { seat: [-1.52, -3.55], lamp: [-2.37, -4.33] },
  architect:            { seat: [1.63, -3.55], lamp: [2.49, -4.25] },
  drafter:              { seat: [6.28, -3.41], lamp: [5.14, -4.26] },
  reviewer:             { seat: [5.47, .75], lamp: [4.63, -.31] },
  fengshui_advisor:     { seat: [7.62, .76], lamp: [8.29, -.26] },
  cost_estimator:       { seat: [6.58, 5.15], lamp: [5.30, 4.07] },
  final_reviewer:       { seat: [.82, 5.65], lamp: [-.99, 4.70] },
};

export const visitPoints = [
  {id: "hall-west", kind: "hall", position: [-2.97, 1.62], facing: [0, .4]},
  {id: "hall-east", kind: "hall", position: [2.76, -1.19], facing: [0, .4]},
  {id: "lounge-tea", kind: "lounge", position: [-5.94, 5.81], facing: [-5.23, 5.05]},
  {id: "lounge-window", kind: "lounge", position: [-8.00, 6.06], facing: [-7.38, 5.20]},
  {id: "showcase-left", kind: "gallery", position: [-2.12, .70], facing: rooms.showcase.center},
  {id: "showcase-right", kind: "gallery", position: [2.00, -.28], facing: rooms.showcase.center},
  {id: "showcase-front", kind: "gallery", position: [.86, 1.97], facing: rooms.showcase.center},
  {id: "reception-guest", kind: "peer", position: [-5.16, 1.89], host: "requirements_analyst"},
  {id: "design-guest", kind: "peer", position: [-.76, -3.38], host: "concept_architect"},
  {id: "drawing-guest", kind: "peer", position: [7.40, -3.24], host: "drafter"},
  {id: "review-guest", kind: "peer", position: [4.64, 1.66], host: "reviewer"},
  {id: "archive-guest", kind: "peer", position: [1.86, 5.88], host: "final_reviewer"},
];

const plank = ["#cfab83", "#d7b58e", "#dfbe96", "#e1c29e", "#d8ba96", "#cfb08b", "#e5c7a5"];

function canvasTexture(width, height, paint) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  paint(context, width, height);
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  return map;
}

function oakTexture() {
  let seed = 67;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  return canvasTexture(960, 672, (c, width, height) => {
    for (let z = 0; z < height; z += 24) {
      for (let x = -Math.floor(random() * 145); x < width;) {
        const length = Math.floor(84 + random() * 177);
        c.fillStyle = plank[Math.floor(random() * plank.length)];
        c.fillRect(x, z, length + 1, 24);
        c.fillStyle = "#8060474d";
        c.fillRect(x, z, 1, 24);
        c.fillRect(x, z, length, 1);
        for (let j = 0; j < 4; j += 1) {
          const y = z + 2 + random() * 20;
          c.strokeStyle = j % 2 ? "#f8e0b738" : "#99704927";
          c.beginPath();
          c.moveTo(x + 2, y);
          c.quadraticCurveTo(x + length * .45, y - 2 + random() * 4, x + length - 2, y);
          c.stroke();
        }
        x += length;
      }
    }
  });
}

function groundShadow() {
  return canvasTexture(128, 128, (c) => {
    const g = c.createRadialGradient(64, 64, 12, 64, 64, 64);
    g.addColorStop(0, "#23433ab7");
    g.addColorStop(.49, "#23433a68");
    g.addColorStop(1, "#23433a00");
    c.fillStyle = g;
    c.fillRect(0, 0, 128, 128);
  });
}

function writePanel(c, name, bg, k = "#d9eee1") {
  c.fillStyle = bg;
  c.fillRect(0, 0, 512, 256);
  c.fillStyle = k;
  c.font = "700 27px system-ui";
  c.fillText(name, 26, 48);
  c.strokeStyle = k;
  c.globalAlpha = .27;
  c.beginPath();
  c.moveTo(26, 66);
  c.lineTo(486, 66);
  c.stroke();
  c.globalAlpha = 1;
}

function drawScreen(c, kind, data) {
  if (kind === "ideas") {
    writePanel(c, "Ý TƯỞNG KIẾN TRÚC", "#f0e8d6", "#475e54");
    c.fillStyle = "#fffaf0";
    c.fillRect(26, 88, 225, 143);
    c.strokeStyle = "#4b7771";
    c.lineWidth = 5;
    c.strokeRect(50, 121, 167, 79);
    c.beginPath();
    c.moveTo(54, 120);
    c.lineTo(147, 98);
    c.lineTo(222, 121);
    c.moveTo(85, 201);
    c.lineTo(85, 138);
    c.lineTo(121, 138);
    c.lineTo(121, 201);
    c.stroke();
    ["#9ab6a0", "#d19b75", "#b3bbd0", "#d5b36b"].forEach((color, i) => {
      c.fillStyle = color;
      c.fillRect(273 + (i % 2) * 105, 88 + Math.floor(i / 2) * 69, 93, 60);
    });
  } else if (kind === "progress") {
    writePanel(c, "TIẾN ĐỘ THIẾT KẾ", "#203c36");
    c.strokeStyle = "#749589";
    c.lineWidth = 4;
    c.beginPath();
    c.moveTo(43, 137);
    c.lineTo(469, 137);
    c.stroke();
    for (let i = 0; i < 9; i += 1) {
      const status = data?.agents[i]?.status;
      c.fillStyle = status === "done" ? "#7bd5b5" : status === "feedback" ? "#e6ad54"
        : ["running", "revising", "awaiting_approval"].includes(status) ? "#f2c881" : "#5e8074";
      c.beginPath();
      c.arc(43 + i * 53.2, 137, 13, 0, Math.PI * 2);
      c.fill();
    }
    c.fillStyle = "#cbe2d5";
    c.font = "21px system-ui";
    const detail = data?.run.iteration;
    c.fillText(Number.isInteger(detail) ? "Vòng sửa · " + detail + " / " + data.run.max_iterations
      : "Chưa có tiến độ lượt thiết kế", 42, 212);
  } else if (kind === "finance") {
    writePanel(c, "DỰ TOÁN CHI PHÍ", "#233e42");
    const amounts = data?.cost_amounts || [];
    const highest = Math.max(...amounts, 1);
    c.strokeStyle = "#789e9e";
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(43, 90);
    c.lineTo(43, 219);
    c.lineTo(475, 219);
    c.stroke();
    if (!amounts.length) {
      c.fillStyle = "#b1ceca";
      c.font = "25px system-ui";
      c.fillText("Chưa có dự toán", 126, 160);
    } else {
      const step = 407 / amounts.length;
      amounts.forEach((value, i) => {
        const h = 120 * value / highest;
        c.fillStyle = i % 2 === 0 ? "#81c3b2" : "#d6b480";
        c.fillRect(53 + step * i, 218 - h, step * .66, h);
      });
    }
  } else if (kind === "blueprint") {
    writePanel(c, "BÀN KỸ THUẬT", "#223f59", "#d4e8ea");
    c.strokeStyle = "#548598";
    c.lineWidth = 1;
    for (let x = 32; x <= 480; x += 22) c.strokeRect(x, 80, 22, 154);
    for (let y = 80; y <= 212; y += 22) c.strokeRect(32, y, 440, 22);
    c.strokeStyle = "#cbebed";
    c.lineWidth = 4;
    c.strokeRect(76, 105, 350, 106);
    c.strokeRect(245, 105, 64, 106);
    c.strokeRect(76, 161, 169, 50);
    c.fillStyle = "#efcc86";
    c.fillRect(309, 156, 117, 5);
  } else {
    writePanel(c, kind === "review" ? "THẨM ĐỊNH" : "HỒ SƠ", "#294a45");
    c.fillStyle = "#d3ebda";
    for (let y = 91; y <= 194; y += 33) {
      c.strokeStyle = "#d3ebda";
      c.strokeRect(37, y, 20, 20);
      c.fillRect(77, y + 7, 360 - (y % 80), 5);
    }
  }
}

function roundedTile() {
  const shape = new THREE.Shape();
  const l = -.5, r = .5, b = -.5, t = .5, radius = .085;
  shape.moveTo(l + radius, b);
  shape.lineTo(r - radius, b);
  shape.quadraticCurveTo(r, b, r, b + radius);
  shape.lineTo(r, t - radius);
  shape.quadraticCurveTo(r, t, r - radius, t);
  shape.lineTo(l + radius, t);
  shape.quadraticCurveTo(l, t, l, t - radius);
  shape.lineTo(l, b + radius);
  shape.quadraticCurveTo(l, b, l + radius, b);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 1, steps: 1, bevelEnabled: false, curveSegments: 3,
  });
  geometry.translate(0, 0, -.5);
  geometry.rotateX(-Math.PI / 2);
  return geometry;
}

function kit() {
  const materials = new Map();
  const geometry = {
    box: new THREE.BoxGeometry(1, 1, 1),
    tile: roundedTile(),
    cylinder: new THREE.CylinderGeometry(.5, .5, 1, 16),
    pot: new THREE.CylinderGeometry(.5, .36, 1, 14),
    sphere: new THREE.SphereGeometry(.5, 12, 9),
    plane: new THREE.PlaneGeometry(1, 1),
    ring: new THREE.RingGeometry(.43, .5, 30).rotateX(-Math.PI / 2),
  };
  const shadow = new THREE.MeshBasicMaterial({map: groundShadow(), depthWrite: false, transparent: true});
  const glass = new THREE.MeshStandardMaterial({color: "#94c6b8", roughness: .32, transparent: true,
    opacity: .25, depthWrite: false, side: THREE.DoubleSide});
  const woodFloor = new THREE.MeshStandardMaterial({map: oakTexture(), roughness: .96});
  const material = (color) => {
    if (typeof color !== "string") return color;
    if (!materials.has(color)) materials.set(color, new THREE.MeshStandardMaterial({color, roughness: .83}));
    return materials.get(color);
  };
  const mesh = (parent, shape, color, x, y, z, w, h, d) => {
    const obj = new THREE.Mesh(geometry[shape], material(color));
    obj.position.set(x, y, z);
    obj.scale.set(w, h, d);
    parent.add(obj);
    return obj;
  };
  const box = (parent, color, x, y, z, w, h, d) => mesh(parent, "box", color, x, y, z, w, h, d);
  const tile = (parent, color, x, y, z, w, h, d) => mesh(parent, "tile", color, x, y, z, w, h, d);
  const cylinder = (parent, color, x, y, z, diameter, height) =>
    mesh(parent, "cylinder", color, x, y, z, diameter, height, diameter);
  const floor = (parent, color, x, y, z, w, depth) => {
    const obj = mesh(parent, "plane", color, x, y, z, w, depth, 1);
    obj.rotation.x = -Math.PI / 2;
    return obj;
  };
  const shade = (parent, x, z, w, d, y = .029) => floor(parent, shadow, x, y, z, w, d);
  return {mesh, geometry, material, glass, woodFloor, box, tile, cylinder, floor, shade};
}

const palette = {
  timber: "#c89868", edge: "#946b4c", metal: "#253a43", paper: "#f6f5f1", plaster: "#ebe4d6",
  teal: "#278b9a", tealDark: "#167d8d", peach: "#cc9e79", cream: "#d8cfba",
  terracotta: "#ba795d", graphite: "#334a4b", leaf: "#437e61",
};

function planter(k, parent, x, z, size = 1) {
  const plant = new THREE.Group();
  plant.position.set(x, 0, z);
  plant.scale.setScalar(size);
  parent.add(plant);
  k.shade(plant, .06, .09, 1.30, 1.12, .033);
  k.mesh(plant, "pot", "#e4bc98", 0, .25, 0, .52, .46, .52);
  k.cylinder(plant, "#6d5b43", 0, .49, 0, .43, .027);
  k.cylinder(plant, "#46644c", 0, .67, 0, .045, .36);
  for (let i = 0; i < 9; i += 1) {
    const theta = i * 2.39996;
    const r = .12 + (i % 3) * .065;
    const leaf = k.mesh(plant, "sphere", [palette.leaf, "#759771", "#315f51"][i % 3],
      Math.cos(theta) * r, .65 + i * .066, Math.sin(theta) * r, .22, .39, .12);
    leaf.rotation.set(Math.sin(theta) * .67, theta, Math.cos(theta) * .67);
  }
}

function desk(k, parent, x, z, w, d, tabletop = palette.timber) {
  k.shade(parent, x + .13, z + .17, w * 1.34, d * 1.75);
  k.tile(parent, palette.edge, x, .71, z, w * .99, .105, d);
  k.tile(parent, tabletop, x, .783, z, w, .057, d * 1.025);
  for (const dx of [-w * .42, w * .42]) {
    for (const dz of [-d * .35, d * .35]) {
      k.box(parent, palette.metal, x + dx, .35, z + dz, .088, .71, .088);
    }
    k.box(parent, palette.metal, x + dx, .33, z, .082, .048, d * .74);
  }
}

function chair(k, parent, x, z, angle, color = palette.teal) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  g.rotation.y = angle;
  parent.add(g);
  k.shade(g, -.02, .04, .97, 1.02);
  k.tile(g, color, 0, .435, 0, .49, .12, .50);
  const back = k.tile(g, color, 0, .68, .242, .47, .30, .118);
  back.rotation.x = -.14;
  k.cylinder(g, palette.metal, 0, .22, 0, .065, .36);
  k.box(g, palette.metal, 0, .084, 0, .48, .047, .075);
  k.box(g, palette.metal, 0, .084, 0, .075, .047, .48);
  for (const [dx, dz] of [[-.225, 0], [.225, 0], [0, -.225], [0, .225]]) {
    k.cylinder(g, palette.metal, dx, .051, dz, .085, .075);
  }
}

function papers(k, parent, x, z, y = .827, turn = 0, color = palette.paper) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  g.rotation.y = turn;
  parent.add(g);
  k.box(g, color, 0, .014, 0, .43, .038, .32);
  for (let i = 0; i < 3; i += 1) {
    k.box(g, "#9eb7aa", -.04 + .02 * i, .035, -.072 + i * .07, .26 - i * .025, .004, .013);
  }
}

function stationery(k, parent, x, z, y = .818) {
  k.cylinder(parent, "#ab7056", x, y + .065, z, .145, .14);
  for (let i = 0; i < 3; i += 1) {
    const pencil = k.cylinder(parent, ["#caa260", "#406e67", "#b48d82"][i], x - .035 + .035 * i,
      y + .141, z, .022, .18 + i * .036);
    pencil.rotation.z = (i - 1) * .24;
  }
}

function uprightScreen(k, parent, kind, x, y, z, w, h, onDesk = false) {
  const texture = canvasTexture(512, 256, (c) => drawScreen(c, kind));
  const surface = new THREE.MeshBasicMaterial({map: texture});
  k.tile(parent, palette.metal, x, y, z, w, h, .107);
  const face = k.mesh(parent, "plane", surface, x, y, z + .063, w * .94, h * .91, 1);
  face.renderOrder = 1;
  if (onDesk) {
    k.box(parent, palette.metal, x, y - h * .49 - .09, z - .015, .095, .22, .095);
    k.tile(parent, palette.metal, x, .844, z, w * .48, .044, .25);
  } else {
    k.box(parent, "#9a795b", x, y - h * .5 - .022, z + .046, w * 1.06, .044, .17);
  }
  return {texture, kind};
}

function frame(k, root, axis, x, z, length, height, glazed = false) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  g.rotation.y = axis === "z" ? Math.PI / 2 : 0;
  root.add(g);
  const h = glazed ? .13 : height;
  k.box(g, glazed ? palette.metal : palette.plaster, 0, h * .5, 0, length, h, .108);
  k.box(g, glazed ? palette.metal : palette.timber, 0, height, 0, length + .025, .054, .137);
  if (glazed) {
    k.box(g, k.glass, 0, (h + height) * .5, 0, length - .035, height - h, .02);
    const count = Math.max(1, Math.ceil(length / 1.8));
    for (let n = 0; n <= count; n += 1) {
      k.box(g, palette.metal, -length * .5 + length * n / count, height * .5, 0, .048, height, .092);
    }
  }
}

function doorway(k, root, x, z, angle = 0) {
  const door = new THREE.Group();
  door.position.set(x, 0, z);
  door.rotation.y = angle;
  root.add(door);
  k.box(door, "#a78155", 0, .011, 0, 1.03, .025, .155);
  for (const offset of [-.51, .51]) k.box(door, palette.metal, offset, .35, 0, .058, .70, .095);
  const panel = new THREE.Group();
  panel.position.x = -.49;
  panel.rotation.y = -Math.PI * .5;
  door.add(panel);
  k.box(panel, k.glass, .335, .38, 0, .65, .65, .036);
  for (const offset of [0, .66]) k.box(panel, palette.metal, offset, .38, 0, .045, .72, .078);
  for (const y of [.042, .73]) k.box(panel, palette.metal, .33, y, 0, .72, .041, .07);
  k.box(panel, "#c5ab78", .56, .43, .046, .14, .037, .031);
}

function partition(k, root, axis, line, start, end, openings, height) {
  let edge = start;
  for (const center of [...openings, end + .55]) {
    const until = center - .55;
    if (until > edge) {
      const mid = (edge + until) * .5;
      frame(k, root, axis, axis === "x" ? mid : line, axis === "x" ? line : mid, until - edge, height, true);
    }
    if (center <= end) {
      doorway(k, root, axis === "x" ? center : line, axis === "x" ? line : center,
        axis === "x" ? 0 : Math.PI / 2);
    }
    edge = center + .55;
  }
}

function shelves(k, parent, x, z) {
  const colors = ["#b47858", "#9fb69a", "#547d74", "#d0ab6f", "#71899c", "#eeeece"];
  for (const side of [-1, 1]) k.box(parent, palette.metal, x + side * 1.28, .89, z, .095, 1.79, .46);
  for (const y of [.16, .70, 1.24, 1.77]) k.box(parent, palette.timber, x, y, z, 2.65, .068, .46);
  for (let row = 0; row < 3; row += 1) {
    for (let i = 0; i < 11; i += 1) {
      const bx = x - 1.1 + i * .205;
      const by = .38 + row * .54;
      k.box(parent, colors[(i * 3 + row) % colors.length], bx, by, z + .014, .175, .34, .33);
      k.box(parent, palette.paper, bx, by + .045, z + .189, .093, .056, .012);
    }
  }
}

function bench(k, parent, x, z, angle, color) {
  const b = new THREE.Group();
  b.position.set(x, 0, z);
  b.rotation.y = angle;
  parent.add(b);
  k.shade(b, .10, .12, 2.6, 1.51);
  k.tile(b, palette.metal, 0, .20, 0, 2.12, .20, .72);
  k.tile(b, color, 0, .365, -.05, 2.20, .16, .75);
  k.tile(b, color, 0, .58, .35, 2.20, .48, .18);
  for (const x of [-1.02, 1.02]) k.tile(b, color, x, .50, -.05, .19, .20, .78);
}

function studioFurniture(k, root) {
  const screens = {};
  k.tile(root, "#233d38", 0, -.455, 0, 19.8, .67, 13.73);
  k.tile(root, "#5fa393", 0, -.68, 0, 19.79, .075, 13.74);
  k.tile(root, "#cfaa82", 0, -.143, 0, 19.64, .16, 13.57);
  k.floor(root, k.woodFloor, 0, -.06, 0, 19.44, 13.32);
  k.shade(root, .65, .7, 28, 21, -.81);
  k.shade(root, .12, .18, 24, 17.6, -.809);
  const rugColors = ["#d5d8b8", "#ccae90", "#c1cdb8", "#9eacaf", "#d0b2a1", "#bcc5ad", "#ccc6ae", "#b5c8ab"];
  Object.entries(rooms).filter(([id]) => id !== "showcase").forEach(([, room], i) => {
    k.tile(root, rugColors[i], room.center[0], .002, room.center[1], room.width, .035, room.depth);
  });
  k.tile(root, "#a8bdaa", 0, -.047, -1.80, 18.75, .026, .69);
  k.tile(root, "#a8bdaa", 3.70, -.045, 2.36, .69, .028, 7.66);
  k.tile(root, "#a8bdaa", -3.66, -.045, .62, .63, .028, 5.40);
  k.tile(root, "#dbc9a3", 0, -.033, 2.57, 6.64, .027, .43);

  frame(k, root, "x", 0, -6.45, 19.26, 2.03, true);
  frame(k, root, "z", -9.58, -3.98, 4.90, 1.54, true);
  frame(k, root, "z", -9.58, 4.41, 4.14, 1.30, true);
  frame(k, root, "z", 9.60, .01, 12.9, .61, true);
  frame(k, root, "x", 0, 6.54, 19.23, .16);
  for (const x of [-3.46, 3.48]) frame(k, root, "z", x, -4.42, 3.86, 1.07, true);
  partition(k, root, "x", rooms.design.door[1], -9.58, 9.60,
    [rooms.management, rooms.design, rooms.drawing].map((room) => room.door[0]), .83);
  partition(k, root, "z", rooms.reception.door[0], -2.51, 4.64, [rooms.reception.door[1]], .71);
  partition(k, root, "z", rooms.review.door[0], -2.51, 6.54, [rooms.review.door[1], rooms.finance.door[1]], .78);
  frame(k, root, "x", 6.67, 2.38, 5.85, .87, true);
  frame(k, root, "x", -6.625, 4.64, 5.91, .63, true);
  partition(k, root, "x", rooms.archive.door[1], -2.64, 2.94, [rooms.archive.door[0]], .48);
  frame(k, root, "z", -2.64, 4.77, 3.55, .48, true);
  frame(k, root, "z", 2.94, 4.77, 3.55, .48, true);
  k.tile(root, "#b5966e", -9.65, -.031, .82, .42, .044, 2.44);

  // Điều hành: bàn họp, bảng tiến độ và góc ngồi trao đổi.
  desk(k, root, -6.45, -4.52, 3.65, 1.12);
  for (const x of [-7.56, -6.44, -5.36]) chair(k, root, x, -5.34, Math.PI);
  for (const x of [-7.58, -5.28]) chair(k, root, x, -3.67, 0, "#b0a481");
  papers(k, root, -6.55, -4.47, .825, -.24);
  papers(k, root, -5.45, -4.42, .824, .14, "#e6eee1");
  stationery(k, root, -5.13, -4.82);
  screens.progress = uprightScreen(k, root, "progress", -6.43, 1.55, -6.18, 3.55, 1.12);
  planter(k, root, -8.85, -5.60, 1.03);

  // Tiếp nhận: quầy chữ L, ghế chờ và cửa kính bên hông.
  k.shade(root, -6.62, -.12, 4.8, 2.0);
  k.tile(root, palette.tealDark, -6.60, .41, -.25, 3.72, .83, .97);
  k.tile(root, palette.timber, -6.60, .86, -.25, 3.85, .107, 1.02);
  k.tile(root, palette.teal, -8.12, .41, .34, .75, .83, 1.68);
  k.tile(root, palette.timber, -8.12, .86, .33, .80, .107, 1.77);
  k.box(root, "#d5bf89", -6.62, .61, .25, 2.75, .032, .044);
  papers(k, root, -6.91, -.10, .918, .16);
  papers(k, root, -5.60, -.22, .918, -.14, "#d8e9dc");
  bench(k, root, -6.79, 3.65, .05, "#82a69a");
  bench(k, root, -8.45, 2.61, Math.PI / 2, "#b49c7e");
  k.cylinder(root, palette.metal, -6.61, .19, 2.42, .65, .35);
  k.cylinder(root, "#e4d1a1", -6.61, .39, 2.42, .89, .104);
  papers(k, root, -6.62, 2.48, .454, .32, "#f1ece0");
  planter(k, root, -4.40, 3.72, 1.11);
  planter(k, root, -8.88, 5.79, 1.14);

  // Thiết kế: phác thảo trên bàn gỗ, bảng vật liệu và ghế thấp.
  desk(k, root, -1.61, -4.52, 2.83, 1.01);
  desk(k, root, 1.61, -4.48, 2.82, 1.09, "#cfac78");
  screens.ideas = uprightScreen(k, root, "ideas", .02, 1.53, -6.19, 4.3, 1.22);
  const drawingBoard = k.tile(root, "#eee7d5", -1.70, .875, -4.52, 1.03, .085, .61);
  drawingBoard.rotation.x = -.13;
  papers(k, root, -.79, -4.70, .824, -.13, "#d9e8d8");
  papers(k, root, 1.52, -4.35, .824, .1);
  for (let i = 0; i < 4; i += 1) k.box(root, rugColors[i], 1.03 + i * .25, .84, -4.77, .19, .054, .20);
  stationery(k, root, 2.57, -4.88);
  planter(k, root, -2.86, -5.74, .81);
  planter(k, root, 2.95, -5.68, .81);

  // Bản vẽ: màn hình kỹ thuật, máy in và ống bản vẽ.
  desk(k, root, 6.35, -4.40, 3.40, 1.16, "#c29c69");
  screens.blueprint = uprightScreen(k, root, "blueprint", 6.54, 1.31, -4.78, 1.91, .66, true);
  papers(k, root, 6.15, -4.04, .829, .04);
  k.tile(root, "#726a58", 8.19, .43, -5.59, 1.31, .90, 1.12);
  k.tile(root, "#3b4e4f", 8.18, 1.04, -5.52, 1.19, .29, .94);
  k.box(root, "#c6d7cc", 8.18, 1.19, -5.50, .85, .032, .61);
  for (let i = 0; i < 3; i += 1) {
    k.cylinder(root, "#e4dcc3", 8.81 + i * .22, .42 + .06 * i, -3.48, .155, .74 + i * .12);
  }

  // Thẩm định: hai chỗ soát bản in và hồ sơ.
  desk(k, root, 6.52, -.34, 4.36, .99, "#caa477");
  screens.review = uprightScreen(k, root, "review", 5.85, 1.26, -.62, 1.49, .63, true);
  papers(k, root, 7.53, -.36, .825, .17);
  papers(k, root, 6.98, -.13, .825, -.22, "#e4d4b5");
  k.tile(root, "#e9d5ae", 8.96, .61, -.42, .66, 1.21, .63);
  planter(k, root, 8.75, 1.56, .89);

  // Tài chính: biểu đồ nhận khối lượng thật từ lượt chạy.
  desk(k, root, 6.53, 4.12, 3.62, 1.08, "#bda177");
  screens.finance = uprightScreen(k, root, "finance", 6.68, 1.32, 3.83, 1.89, .73, true);
  papers(k, root, 5.87, 4.38, .827, .19);
  k.tile(root, "#768b74", 8.58, .40, 4.01, .82, .85, .72);
  stationery(k, root, 7.81, 4.32);
  planter(k, root, 8.73, 5.63, 1.01);

  // Kiểm soát hồ sơ: gáy tài liệu và bàn đóng gói.
  shelves(k, root, -1.29, 3.44);
  desk(k, root, -.05, 4.71, 3.85, 1.04, "#c8a877");
  screens.archive = uprightScreen(k, root, "archive", .76, 1.27, 4.43, 1.26, .62, true);
  k.tile(root, "#bd926b", -1.29, .988, 4.63, .79, .34, .66);
  k.box(root, "#e6c89c", -1.29, 1.16, 4.63, .11, .018, .66);
  papers(k, root, -.35, 4.94, .83, .15);
  planter(k, root, -2.59, 5.64, .84);

  // Kệ trung tâm và khoảng tiếp cận chung.
  k.shade(root, .01, .40, 3.9, 3.15);
  k.tile(root, "#789788", -.07, .018, .26, 3.77, .048, 2.85);
  k.tile(root, palette.tealDark, -.07, .27, .26, 2.92, .49, 2.07);
  k.tile(root, "#bf9d6f", -.07, .525, .26, 3.19, .114, 2.29);
  k.tile(root, palette.paper, -.07, .60, .26, 3.26, .053, 2.36);
  k.box(root, "#d2b27f", -.07, .27, 1.309, 1.10, .076, .023);
  planter(k, root, -2.70, -.70, .78);
  planter(k, root, 2.55, .92, .77);

  // Góc nghỉ mở ra lối đi phía trước, tách khỏi cửa khu tiếp nhận.
  bench(k, root, -7.48, 5.26, Math.PI, "#739c86");
  k.cylinder(root, palette.metal, -5.23, .17, 5.05, .46, .31);
  k.cylinder(root, "#dfc397", -5.23, .37, 5.05, .65, .085);
  k.cylinder(root, "#f0ead6", -5.23, .46, 5.05, .14, .105);
  planter(k, root, -3.88, 6.13, .61);
  return screens;
}

function lamp(k, x, z, color, y) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  k.cylinder(g, palette.metal, 0, .025, 0, .25, .042);
  k.cylinder(g, palette.metal, 0, .19, 0, .046, .31);
  const hood = new THREE.MeshStandardMaterial({color, emissive: "#ffc77a", emissiveIntensity: 0, roughness: .7});
  k.mesh(g, "pot", hood, -.12, .37, 0, .30, .18, .30).rotation.z = -.74;
  const lit = new THREE.MeshBasicMaterial({color: "#ffe3a9", transparent: true, opacity: .0, depthWrite: false});
  const pool = k.floor(g, lit, -.135, .013, .015, .34, .25);
  pool.renderOrder = 2;
  return {group: g, hood, lit};
}

function avatar(k, deskData, agent, index) {
  const actor = new THREE.Group();
  actor.position.set(deskData.seat[0], 0, deskData.seat[1]);
  actor.rotation.y = -.18 + .31 * (index % 3);
  const body = new THREE.Group();
  actor.add(body);
  const skin = ["#d9a986", "#bb8066", "#e3b999", "#a46e52"][index % 4];
  const hair = ["#383c35", "#47342c", "#332e2b"][index % 3];
  const coat = agent.color;
  k.shade(actor, 0, 0, .61, .67, .036);
  const ringMat = new THREE.MeshBasicMaterial({color: agent.color, transparent: true, opacity: .58, depthWrite: false});
  const ring = k.mesh(actor, "ring", ringMat, 0, .043, 0, .65, 1, .65);
  const legs = [-.083, .083].map((dx) => {
    const hip = new THREE.Group();
    hip.position.set(dx, .38, 0);
    body.add(hip);
    k.tile(hip, "#495a59", 0, -.088, 0, .128, .176, .15);
    const knee = new THREE.Group();
    knee.position.y = -.173;
    hip.add(knee);
    k.tile(knee, "#495a59", 0, -.075, 0, .123, .167, .14);
    k.tile(knee, palette.metal, 0, -.134, .032, .126, .108, .23);
    return {hip, knee};
  });
  k.mesh(body, "pot", coat, 0, .51, 0, .34, .38, .225);
  k.box(body, "#ebd8a4", .062, .588, .113, .056, .063, .012);
  k.cylinder(body, skin, 0, .734, 0, .104, .129);
  k.mesh(body, "sphere", skin, 0, .875, .014, .288, .30, .268);
  k.mesh(body, "sphere", hair, -.008, .967, -.022, .298, .136, .263);
  k.mesh(body, "sphere", hair, -.102, .899, -.034, .11, .192, .178);
  if (index % 3 === 1) k.mesh(body, "sphere", hair, -.08, 1.018, -.064, .127, .122, .127);
  for (const dx of [-.052, .052]) k.mesh(body, "sphere", "#282a24", dx, .878, .141, .025, .029, .019);
  const right = new THREE.Group();
  const left = new THREE.Group();
  const grips = new Map();
  right.position.set(.177, .645, 0);
  left.position.set(-.177, .645, 0);
  for (const [arm, sign] of [[right, 1], [left, -1]]) {
    arm.rotation.z = sign * .16;
    k.mesh(arm, "sphere", coat, 0, -.10, 0, .118, .29, .128);
    k.mesh(arm, "sphere", skin, 0, -.237, .012, .103, .121, .103);
    const grip = new THREE.Group();
    grip.position.set(0, -.237, .035);
    arm.add(grip);
    grips.set(arm === right ? "right" : "left", grip);
    body.add(arm);
  }
  const signal = k.mesh(actor, "sphere", new THREE.MeshBasicMaterial({color: "#a86424"}),
    .26, 1.02, 0, .13, .13, .13);
  signal.visible = false;
  return {group: actor, body, right, left, legs, ring, ringMat, signal, grips, home: deskData.seat};
}

function floorFootprints(stage) {
  const bounds = new THREE.Box3();
  const obstacles = [];
  stage.updateMatrixWorld(true);
  stage.traverse((obj) => {
    if (!obj.isMesh) return;
    if (!obj.geometry.boundingBox) obj.geometry.computeBoundingBox();
    bounds.copy(obj.geometry.boundingBox).applyMatrix4(obj.matrixWorld);
    if (bounds.max.y < .12 || bounds.min.y > .81 || bounds.max.y - bounds.min.y < .031) return;
    obstacles.push([bounds.min.x, bounds.min.z, bounds.max.x, bounds.max.z]);
  });
  return obstacles;
}

function batchOpaque(root) {
  const groups = new Map();
  root.updateMatrixWorld(true);
  root.traverse((obj) => {
    if (!obj.isMesh || obj.material.transparent || obj.renderOrder) return;
    const key = obj.geometry.uuid + obj.material.uuid;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(obj);
  });
  for (const group of groups.values()) {
    if (group.length < 3) continue;
    const batch = new THREE.InstancedMesh(group[0].geometry, group[0].material, group.length);
    group.forEach((obj, i) => {
      batch.setMatrixAt(i, obj.matrixWorld);
      obj.removeFromParent();
    });
    batch.computeBoundingSphere();
    root.add(batch);
  }
}

function illustrativeHouse(k, root) {
  k.tile(root, "#8eb29c", 0, .018, 0, 2.85, .04, 1.87);
  k.tile(root, "#e1ceb0", 0, .06, 0, 2.48, .086, 1.48);
  k.box(root, "#e9e7cf", -.15, .33, 0, 1.94, .50, 1.30);
  k.box(root, "#f4efe0", -.50, .73, -.01, 1.27, .43, 1.23);
  k.box(root, "#7eaaa6", -.30, .35, .656, 1.42, .34, .026);
  k.box(root, "#8db7ad", -.56, .74, .616, 1.0, .31, .035);
  k.box(root, "#427571", .825, .34, -.05, .039, .34, .86);
  for (const x of [-.95, -.45, .06, .41]) k.box(root, "#a88661", x, .35, .674, .037, .38, .061);
  k.box(root, "#344c45", -.44, .98, 0, 1.59, .085, 1.49);
  k.box(root, "#344c45", .61, .61, 0, .82, .075, 1.48);
  k.box(root, "#c39c68", .64, .64, .34, .61, .055, .62);
  for (const x of [.40, .58, .76, .93]) k.box(root, "#866b4b", x, .34, .697, .038, .56, .038);
  planter(k, root, 1.11, -.53, .25);
  planter(k, root, -1.21, .62, .20);
}

function layoutHouse(k, root, geometry) {
  const vertical = geometry.floors.reduce((sum, floor) => sum + floor.height, 0);
  const scale = Math.min(2.45 / geometry.width, 1.87 / geometry.depth, 2.02 / vertical);
  const colors = ["#9abca7", "#b1bea3", "#80a7a0", "#a1b7cb", "#c0af91"];
  const w = geometry.width * scale;
  const d = geometry.depth * scale;
  k.tile(root, "#e1ceae", 0, .035, 0, w + .14, .070, d + .14);
  let elevation = .07;
  geometry.floors.forEach((floor, index) => {
    const h = floor.height * scale;
    for (const room of floor.rooms) {
      if (room.kind === "san" || room.kind === "gieng_troi") continue;
      const x = (room.x + room.w * .5) * scale - w * .5;
      const z = (room.z + room.d * .5) * scale - d * .5;
      const open = ["ban_cong", "san_phoi"].includes(room.kind);
      const thickness = Math.min(.028, h * .13);
      const width = room.w * scale, depth = room.d * scale;
      k.box(root, "#f5efdb", x, elevation + thickness * .5, z, width, thickness, depth);
      if (!open) {
        const gap = Math.min(.014, width * .11, depth * .11);
        k.box(root, colors[index % colors.length], x, elevation + h * .5 + thickness * .5, z,
          width - gap, h - thickness, depth - gap);
      }
    }
    elevation += h;
  });
}

export function buildOffice(scene, agents) {
  const k = kit();
  const stage = new THREE.Group();
  scene.add(stage);
  const screens = studioFurniture(k, stage);
  const footprints = floorFootprints(stage);
  // Ghế thuộc từng chỗ ngồi. Điều hướng giữ chỗ riêng, để chủ ghế có thể ngồi vào.
  for (const agent of agents) {
    const [x, z] = desks[agent.id].seat;
    k.cylinder(stage, palette.metal, x, .16, z, .10, .30);
    k.cylinder(stage, palette.metal, x, .045, z, .35, .045);
    k.tile(stage, agent.color, x, .315, z, .40, .075, .37);
  }
  batchOpaque(stage);
  const figures = new Map();
  const picks = [];
  const invisible = new THREE.MeshBasicMaterial({visible: false});
  for (const [id, room] of Object.entries(rooms)) {
    const hit = k.box(scene, invisible, room.center[0], .071, room.center[1], room.width, .08, room.depth);
    hit.userData.roomId = id;
    picks.push(hit);
  }
  agents.forEach((agent, i) => {
    const deskData = desks[agent.id];
    const figure = avatar(k, deskData, agent, i);
    const luminaire = lamp(k, ...deskData.lamp, agent.color, agent.room === "reception" ? .922 : .816);
    scene.add(figure.group, luminaire.group);
    const hit = k.box(figure.group, invisible, 0, .59, 0, .60, 1.25, .63);
    hit.userData.agentId = agent.id;
    picks.unshift(hit);
    figures.set(agent.id, {...figure, luminaire, phase: i * .79});
  });

  const house = new THREE.Group();
  house.position.set(rooms.showcase.center[0], .626, rooms.showcase.center[1]);
  scene.add(house);
  let houseKey;
  function updateHouse(geometry) {
    const key = JSON.stringify(geometry);
    if (houseKey === key) return false;
    houseKey = key;
    house.clear();
    if (geometry) layoutHouse(k, house, geometry);
    else illustrativeHouse(k, house);
    return true;
  }
  let screenKey;
  function updateScreens(data) {
    const key = JSON.stringify([data.cost_amounts, data.run, data.agents.map((agent) => agent.status)]);
    if (key === screenKey) return false;
    screenKey = key;
    for (const role of ["finance", "progress"]) {
      const {texture, kind} = screens[role];
      drawScreen(texture.image.getContext("2d"), kind, data);
      texture.needsUpdate = true;
    }
    return true;
  }
  return {k, picks, figures, footprints, updateHouse, updateScreens};
}
