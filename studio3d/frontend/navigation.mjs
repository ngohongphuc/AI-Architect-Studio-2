/* Điều hướng trên mặt sàn X/Z. Dấu vết được giữ theo đoạn để các lượt đi không giao nhau. */
export const PERSONAL_SPACE = .56;
const STEP = .24;
const CLEARANCE = .18;
const LEFT = -9.36, TOP = -6.24, COLS = 79, ROWS = 53;
const BIN = 1.2;
const DIRECTIONS = [-1, 0, 1].flatMap((x) => [-1, 0, 1].map((z) => [x, z]))
  .filter(([x, z]) => x || z);

export const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

function pointDistanceSquared(point, a, b) {
  const dx = b[0] - a[0], dz = b[1] - a[1];
  const length = dx * dx + dz * dz;
  const t = length ? Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dz) / length)) : 0;
  return (point[0] - a[0] - t * dx) ** 2 + (point[1] - a[1] - t * dz) ** 2;
}

function hitsRect(a, b, rect) {
  let lo = 0, hi = 1;
  for (let axis = 0; axis < 2; axis++) {
    const change = b[axis] - a[axis];
    const lower = rect[axis], upper = rect[axis + 2];
    if (!change) {
      if (a[axis] < lower || a[axis] > upper) return false;
      continue;
    }
    const first = (lower - a[axis]) / change, second = (upper - a[axis]) / change;
    lo = Math.max(lo, Math.min(first, second));
    hi = Math.min(hi, Math.max(first, second));
    if (lo > hi) return false;
  }
  return true;
}

class Heap {
  items = [];

  push(item) {
    const items = this.items;
    let index = items.length;
    while (index > 0) {
      const parent = (index - 1) >> 1;
      if (items[parent][1] <= item[1]) break;
      items[index] = items[parent];
      index = parent;
    }
    items[index] = item;
  }

  pop() {
    const items = this.items, result = items[0], tail = items.pop();
    if (!items.length) return result;
    let i = 0;
    while (i * 2 + 1 < items.length) {
      let child = i * 2 + 1;
      if (child + 1 < items.length && items[child + 1][1] < items[child][1]) child++;
      if (items[child][1] >= tail[1]) break;
      items[i] = items[child];
      i = child;
    }
    items[i] = tail;
    return result;
  }
}

function column(point) { return Math.round((point[0] - LEFT) / STEP); }
function row(point) { return Math.round((point[1] - TOP) / STEP); }

export class WalkMap {
  constructor(footprints) {
    this.bins = new Map();
    for (const [x, z, right, bottom] of footprints) {
      const rect = [x - CLEARANCE, z - CLEARANCE, right + CLEARANCE, bottom + CLEARANCE];
      for (let row = Math.floor(rect[1] / BIN); row <= Math.floor(rect[3] / BIN); row++) {
        for (let col = Math.floor(rect[0] / BIN); col <= Math.floor(rect[2] / BIN); col++) {
          const key = row * 64 + col;
          if (!this.bins.has(key)) this.bins.set(key, []);
          this.bins.get(key).push(rect);
        }
      }
    }
    this.nodes = Array.from({length: COLS * ROWS}, (_, id) =>
      [LEFT + id % COLS * STEP, TOP + Math.floor(id / COLS) * STEP]);
    this.open = this.nodes.map((point) => this.clear(point, point));
    this.links = this.nodes.map((point, id) => {
      if (!this.open[id]) return [];
      const x = id % COLS, z = Math.floor(id / COLS);
      return DIRECTIONS.map(([dx, dz]) => [x + dx, z + dz])
        .filter(([c, r]) => c >= 0 && c < COLS && r >= 0 && r < ROWS)
        .map(([c, r]) => r * COLS + c)
        .filter((target) => this.open[target] && this.clear(point, this.nodes[target]));
    });
  }

  clear(a, b, circles = []) {
    const x = Math.min(a[0], b[0]), right = Math.max(a[0], b[0]);
    const z = Math.min(a[1], b[1]), bottom = Math.max(a[1], b[1]);
    if (x < LEFT || right > LEFT + (COLS - 1) * STEP || z < TOP || bottom > TOP + (ROWS - 1) * STEP) {
      return false;
    }
    for (let row = Math.floor(z / BIN); row <= Math.floor(bottom / BIN); row++) {
      for (let col = Math.floor(x / BIN); col <= Math.floor(right / BIN); col++) {
        if (this.bins.get(row * 64 + col)?.some((rect) => hitsRect(a, b, rect))) return false;
      }
    }
    return !circles.some(([point, radius]) => pointDistanceSquared(point, a, b) < radius * radius);
  }

  find(start, end, circles = []) {
    if (this.clear(start, end, circles)) return distance(start, end) > .001 ? [end] : [];
    const masked = new Uint8Array(this.nodes.length);
    // Khoảng dư trên lưới giữ an toàn cả giữa hai ô chéo.
    for (const [point, clearance] of circles) {
      const radius = clearance + STEP * .63;
      const span = Math.ceil(radius / STEP);
      const x = column(point), z = row(point);
      for (let r = Math.max(0, z - span); r <= Math.min(ROWS - 1, z + span); r++) {
        for (let c = Math.max(0, x - span); c <= Math.min(COLS - 1, x + span); c++) {
          const id = r * COLS + c;
          if (distance(point, this.nodes[id]) < radius) masked[id] = 1;
        }
      }
    }
    const nearest = (position) => {
      const x = column(position), z = row(position);
      const options = [];
      for (let r = Math.max(0, z - 3); r <= Math.min(ROWS - 1, z + 3); r++) {
        for (let c = Math.max(0, x - 3); c <= Math.min(COLS - 1, x + 3); c++) {
          const id = r * COLS + c;
          if (this.open[id] && !masked[id]) options.push(id);
        }
      }
      options.sort((a, b) => distance(position, this.nodes[a]) - distance(position, this.nodes[b]));
      return options.find((id) => this.clear(position, this.nodes[id], circles));
    };
    const first = nearest(start), last = nearest(end);
    if (first === undefined || last === undefined) return null;

    const cost = new Float64Array(this.nodes.length).fill(Infinity);
    const parent = new Int32Array(this.nodes.length).fill(-1);
    const queue = new Heap();
    cost[first] = 0;
    queue.push([first, distance(this.nodes[first], end), 0]);
    while (queue.items.length) {
      const [id, , known] = queue.pop();
      if (id === last) break;
      if (known !== cost[id]) continue;
      for (const next of this.links[id]) {
        if (masked[next]) continue;
        const estimate = known + distance(this.nodes[id], this.nodes[next]);
        if (estimate >= cost[next]) continue;
        cost[next] = estimate;
        parent[next] = id;
        queue.push([next, estimate + distance(this.nodes[next], end), estimate]);
      }
    }
    if (!Number.isFinite(cost[last])) return null;
    const raw = [end];
    for (let id = last; id !== -1; id = parent[id]) raw.push(this.nodes[id]);
    raw.reverse();
    const path = [];
    let from = start;
    for (let i = 0; i < raw.length;) {
      let next = raw.length - 1;
      while (next > i && !this.clear(from, raw[next], circles)) next--;
      if (!this.clear(from, raw[next], circles)) return null;
      from = raw[next];
      path.push(from);
      i = next + 1;
    }
    return path;
  }
}

export function reserve(points) {
  const radius = PERSONAL_SPACE + .06;
  const circles = [[points[0], radius]];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    const steps = Math.max(1, Math.ceil(distance(a, b) / .12));
    for (let step = 1; step <= steps; step++) {
      const t = step / steps;
      circles.push([[a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], radius]);
    }
  }
  return circles;
}
