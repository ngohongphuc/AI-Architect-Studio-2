import { distance, PERSONAL_SPACE, reserve } from "./navigation.mjs";

const FREE = new Set(["waiting", "done", "feedback", "stopped", "skipped"]);
const HOME_FACING = Math.PI;
const RETRY = .45;
const EXCHANGE_TIME = 1.05;
const HANDOVER_AT = .56;
const angleTo = (from, to) => Math.atan2(to[0] - from[0], to[1] - from[1]);

export function deliveryStops(home, inside = () => true) {
  return [0, -1, 1, -2, 2, -3, 3, 4].map((step) => {
    const angle = step * Math.PI / 4;
    return [home[0] + .73 * Math.sin(angle), home[1] - .73 * Math.cos(angle)];
  }).filter(inside);
}

export function approachAngle(current, target, maxStep) {
  const difference = Math.atan2(Math.sin(target - current), Math.cos(target - current));
  return current + Math.max(-maxStep, Math.min(maxStep, difference));
}

// Trạng thái sân khấu cục bộ. Không phát sự kiện hoặc ghi ngược vào trạng thái thiết kế.
export class OfficeActors {
  constructor(navigation, people, places, {random = Math.random, maxVisitors = 2, drop = null} = {}) {
    this.navigation = navigation;
    this.random = random;
    this.maxVisitors = maxVisitors;
    this.time = 0;
    this.nextDeparture = 1.10;
    this.idle = true;
    this.deliveries = new Set();
    this.queue = [];
    this.handoffs = new Map();
    this.seen = new Set();
    this.nextDelivery = 0;
    this.drop = drop;
    this.places = places.filter(({position}) => navigation.clear(position, position));
    this.agents = new Map(people.map(({id, home, status, stops = deliveryStops(home)}, index) => [id, {
      id, home, position: [...home], status, angle: HOME_FACING, facing: HOME_FACING,
      stops: stops.filter((spot) => navigation.clear(spot, home)), handoff: null,
      phase: 0, stride: 0, sitting: 1, atHome: true, trip: null, recall: false,
      nextVisit: 1.5 + index * .42 + random() * 3.7, nextPlan: 0, restUntil: Infinity,
      lastDestination: null,
    }]));
  }

  updateStatuses(people) {
    let changed = false;
    for (const {id, status} of people) {
      const person = this.agents.get(id);
      if (person.status === status) continue;
      person.status = status;
      changed = true;
      if (!FREE.has(status) && !person.handoff) this.recall(person);
      else if (person.atHome) person.nextVisit = this.time + 1.6 + this.random() * 4.2;
    }
    return changed;
  }

  setIdle(enabled) {
    if (this.idle === enabled) return;
    this.idle = enabled;
    for (const person of this.agents.values()) {
      if (!enabled && !person.handoff) this.recall(person);
      else if (person.atHome) person.nextVisit = this.time + 1.3 + this.random() * 4.6;
    }
  }

  setDeliveries(ids) {
    for (const id of ids) {
      const person = this.agents.get(id);
      if (person && !person.handoff && !this.deliveries.has(id)) this.recall(person);
    }
    this.deliveries = ids;
  }

  enqueue(events) {
    let added = false;
    for (const event of events) {
      if (event.pending || event.from === event.to || this.seen.has(event.id) || !this.agents.has(event.from)) continue;
      const receiver = this.agents.get(event.to);
      if (!receiver && !(event.to === "showcase" && this.drop)) continue;
      this.seen.add(event.id);
      this.queue.push({event, sender: this.agents.get(event.from), receiver});
      added = true;
    }
    if (added) {
      this.refreshDeliveries();
      this.nextDelivery = this.time;
    }
    return added;
  }

  refreshDeliveries() {
    const ids = new Set(this.queue.flatMap(({sender, receiver}) => receiver ? [sender.id, receiver.id] : [sender.id]));
    for (const job of this.handoffs.values()) {
      ids.add(job.sender.id);
      if (job.receiver?.handoff === job) ids.add(job.receiver.id);
    }
    this.setDeliveries(ids);
  }

  startDeliveries() {
    if (!this.queue.length || this.handoffs.size >= 2 || this.nextDelivery > this.time) return;
    const earlier = new Set();
    this.queue = this.queue.filter((job) => {
      const {sender, receiver, event} = job;
      const participants = receiver ? [sender, receiver] : [sender];
      const ready = this.handoffs.size < 2 && participants.every((person) =>
        person.atHome && !person.handoff && !earlier.has(person));
      participants.forEach((person) => earlier.add(person));
      if (!ready) return true;
      const stops = receiver?.stops ?? [this.drop.position];
      const blocked = this.blockedByOthers(sender);
      for (const stop of stops) {
        const path = this.navigation.find(sender.position, stop, blocked);
        if (!path?.length) continue;
        this.start(sender, path, "deliver");
        Object.assign(job, {phase: "walking", owner: sender, route: sender.trip.route,
          reservations: sender.trip.reservations, started: this.time});
        sender.handoff = job;
        if (receiver) receiver.handoff = job;
        this.handoffs.set(event.id, job);
        return false;
      }
      // Bàn giao vẫn nằm trong nhật ký nếu cách bố trí hiện tại không có lối đi tĩnh.
      return stops.some((stop) => this.navigation.find(sender.home, stop));
    });
    this.refreshDeliveries();
    this.nextDelivery = this.time + RETRY;
  }

  advanceDeliveries() {
    for (const [id, job] of this.handoffs) {
      const {sender, receiver, phase} = job;
      if (phase === "walking" && !sender.trip) {
        sender.facing = angleTo(sender.position, receiver?.position ?? this.drop.facing);
        if (receiver) receiver.facing = angleTo(receiver.position, sender.position);
        job.phase = "exchanging";
        job.started = this.time;
        job.exchangeUntil = this.time + EXCHANGE_TIME;
      } else if (phase === "exchanging") {
        const elapsed = this.time - job.started;
        if (elapsed >= HANDOVER_AT) job.owner = receiver ?? null;
        if (this.time < job.exchangeUntil) continue;
        job.phase = "returning";
        job.owner = null;
        if (receiver) {
          receiver.handoff = null;
          receiver.facing = HOME_FACING;
        }
        // Tuyến đi được giữ đến khi sender về ghế, nên có thể quay về theo lối cũ.
        this.start(sender, job.route.slice(0, -1).reverse(), "delivery-home");
        this.refreshDeliveries();
      } else if (phase === "returning" && sender.atHome) {
        sender.handoff = null;
        this.handoffs.delete(id);
        this.refreshDeliveries();
      }
    }
  }

  resetDeliveries() {
    this.queue.length = 0;
    for (const {sender, receiver, phase, route} of this.handoffs.values()) {
      if (phase !== "returning") {
        const passed = phase === "walking" && sender.trip ? sender.trip.next : route.length - 1;
        this.start(sender, route.slice(0, passed).reverse(), "delivery-home");
      }
      sender.handoff = null;
      if (receiver?.handoff?.sender === sender) {
        receiver.handoff = null;
        receiver.facing = HOME_FACING;
      }
    }
    this.handoffs.clear();
    this.seen.clear();
    this.refreshDeliveries();
  }

  recall(person) {
    if (person.atHome || person.recall) return;
    person.recall = true;
    person.nextPlan = this.time;
  }

  blockedByOthers(person) {
    const circles = [];
    for (const other of this.agents.values()) {
      if (other === person) continue;
      circles.push([other.home, .43]);
      if (other.handoff?.sender === other) circles.push(...other.handoff.reservations);
      else if (other.trip) circles.push(...other.trip.reservations);
      else circles.push([other.position, PERSONAL_SPACE]);
    }
    return circles;
  }

  start(person, points, purpose, destination = null) {
    if (!points.length) return false;
    const route = [person.position, ...points];
    person.trip = {route, reservations: reserve(route), next: 1, purpose, destination};
    person.atHome = false;
    person.restUntil = Infinity;
    return true;
  }

  returnHome(person) {
    if (["home", "retreat", "delivery-home"].includes(person.trip?.purpose)) return;
    const route = this.navigation.find(person.position, person.home, this.blockedByOthers(person));
    if (route) {
      if (!this.start(person, route, "home")) this.dock(person);
      return;
    }
    if (person.trip) {
      // Khi lối xa hơn đang có người đi, lùi về điểm xuất phát dọc phần đường đã giữ.
      const prefix = person.trip.route.slice(0, person.trip.next).reverse();
      this.start(person, prefix, "retreat");
    }
    person.nextPlan = this.time + RETRY;
  }

  dock(person) {
    person.atHome = true;
    person.recall = false;
    person.facing = HOME_FACING;
    person.nextVisit = this.time + 3.5 + this.random() * 8.2;
  }

  get canVisit() {
    if (!this.idle || this.deliveries.size) return false;
    const people = [...this.agents.values()];
    return !people.some((person) => person.recall)
      && people.filter((person) => !person.atHome).length < this.maxVisitors;
  }

  startVisit() {
    const person = [...this.agents.values()].filter((candidate) =>
      candidate.atHome && FREE.has(candidate.status) && candidate.nextVisit <= this.time)
      .sort((a, b) => a.nextVisit - b.nextVisit)[0];
    if (!person) return;
    const blocked = this.blockedByOthers(person);
    const options = this.places.filter((place) => {
      if (place.id === person.lastDestination?.id) return false;
      const host = this.agents.get(place.host);
      return !host || (host !== person && host.atHome && FREE.has(host.status));
    }).map((place) => ({place, order: this.random() + (place.kind === person.lastDestination?.kind ? .7 : 0)}))
      .sort((a, b) => a.order - b.order);
    for (const {place} of options) {
      const path = this.navigation.find(person.position, place.position, blocked);
      if (path && this.start(person, path, "visit", place)) {
        person.lastDestination = place;
        this.nextDeparture = this.time + .70 + this.random() * 1.3;
        return;
      }
    }
    person.nextVisit = this.time + 1.5 + this.random() * 2;
    this.nextDeparture = this.time + .56;
  }

  move(person, dt) {
    const trip = person.trip;
    const carrying = trip?.purpose === "deliver" || trip?.purpose === "delivery-home";
    const speed = carrying ? 2.55 : person.recall ? 2.25 : 1.70;
    let left = person.sitting < .065 ? dt * speed : 0;
    if (carrying && trip.next === 1 && distance(person.position, trip.route[1]) > .005) {
      person.facing = angleTo(person.position, trip.route[1]);
      if (Math.abs(Math.sin((person.facing - person.angle) / 2)) > .46) left = 0;
    }
    let walked = 0;
    while (trip && trip.next < trip.route.length && left > 0) {
      const goal = trip.route[trip.next], length = distance(person.position, goal);
      if (length > .005) person.facing = angleTo(person.position, goal);
      const step = Math.min(length, left);
      if (length <= left) {
        person.position = goal;
        trip.next++;
      } else {
        const t = step / length;
        person.position = person.position.map((value, axis) => value + (goal[axis] - value) * t);
      }
      walked += step;
      left -= step;
    }
    if (trip && trip.next === trip.route.length) {
      person.trip = null;
      if (trip.purpose === "home" || trip.purpose === "delivery-home") this.dock(person);
      else if (trip.purpose === "retreat") person.nextPlan = this.time;
      else if (trip.purpose === "visit") {
        const target = trip.destination.facing || this.agents.get(trip.destination.host)?.home;
        if (target) person.facing = angleTo(person.position, target);
        person.restUntil = this.time + 1.35 + this.random() * 4.3;
      }
    }
    person.angle = approachAngle(person.angle, person.facing, dt * 8);
    person.sitting = Math.max(0, Math.min(1, person.sitting + (this.seated(person) ? 1 : -1) * dt * 5));
    person.phase += walked * 9.5;
    person.stride = Math.max(0, Math.min(1, person.stride + (walked > .001 ? 1 : -1) * dt * 8));
  }

  advance(elapsed) {
    this.time += elapsed;
    const dt = Math.min(elapsed, .065);
    for (const person of this.agents.values()) {
      if (person.handoff) continue;
      if (person.restUntil <= this.time) this.recall(person);
      if (person.recall && person.nextPlan <= this.time) this.returnHome(person);
    }
    this.startDeliveries();
    if (this.canVisit && this.nextDeparture <= this.time) this.startVisit();
    for (const person of this.agents.values()) this.move(person, dt);
    this.advanceDeliveries();
  }

  seated(person) {
    return person.atHome && person.handoff?.phase !== "exchanging";
  }

  get moving() {
    return this.handoffs.size > 0 || [...this.agents.values()].some((person) => person.trip || person.stride > 0
      || person.sitting !== Number(this.seated(person))
      || Math.abs(Math.sin((person.facing - person.angle) * .5)) > .01);
  }

  get nextWake() {
    let time = this.queue.length ? this.nextDelivery : Infinity;
    const canVisit = this.canVisit;
    for (const person of this.agents.values()) {
      if (!person.recall) time = Math.min(time, person.restUntil);
      else if (!person.trip) time = Math.min(time, person.nextPlan);
      if (canVisit && person.atHome && FREE.has(person.status)) {
        time = Math.min(time, Math.max(this.nextDeparture, person.nextVisit));
      }
    }
    return time - this.time;
  }
}
