import assert from "node:assert/strict";
import test from "node:test";
import { OfficeActors } from "../studio3d/frontend/actors.mjs";
import { distance, PERSONAL_SPACE, WalkMap } from "../studio3d/frontend/navigation.mjs";

const gate = new WalkMap([[-9.5, -.10, -.56, .10], [.56, -.10, 9.5, .10]]);
const makePerson = (id, home, status = "waiting") => ({id, home, status});
const place = (id, position) => ({id, position, kind: "gallery", facing: [0, 4]});

function tickUntil(actors, condition, seconds = 40) {
  for (let i = 0; i < seconds * 30; i++) {
    if (condition()) return;
    actors.advance(1 / 30);
  }
  assert.ok(condition(), "Trạng thái hoạt ảnh chưa đạt đích trong giới hạn kiểm thử");
}

test("tuyến đi qua khe cửa và từng đoạn tránh vật cản", () => {
  const start = [-2.2, -2], end = [-2.3, 2];
  const path = gate.find(start, end);
  assert.ok(path.length > 1);
  const points = [start, ...path];
  let crossed = false;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    assert.ok(gate.clear(a, b));
    if (a[1] < 0 && b[1] >= 0) {
      const x = a[0] + (b[0] - a[0]) * (-a[1]) / (b[1] - a[1]);
      assert.ok(Math.abs(x) < .39);
      crossed = true;
    }
  }
  assert.ok(crossed);
});

test("nhận việc ngay khi avatar đi dạo, rồi quay về bàn từng bước", () => {
  const person = makePerson("architect", [-2.3, -2]);
  const actors = new OfficeActors(gate, [person], [place("model", [2, 2.5])], {random: () => .25});
  const avatar = actors.agents.get(person.id);
  tickUntil(actors, () => avatar.trip?.purpose === "visit" && distance(avatar.home, avatar.position) > 1.1);
  const walking = [...avatar.position];
  assert.ok(actors.updateStatuses([{id: person.id, status: "running"}]));
  assert.equal(avatar.status, "running");
  assert.deepEqual(avatar.position, walking);
  actors.advance(1 / 30);
  assert.equal(avatar.trip.purpose, "home");
  assert.ok(distance(walking, avatar.position) < .09);
  tickUntil(actors, () => avatar.atHome && avatar.sitting === 1);
  assert.deepEqual(avatar.position, avatar.home);
});

test("ba agent dùng chung cửa, giữ khoảng cách và cuối cùng đều đi qua", () => {
  const people = [makePerson("a", [-2.1, -1.8]), makePerson("b", [2.1, -1.8]), makePerson("c", [0, -3.4])];
  const spots = [place("p1", [-2.0, 2.5]), place("p2", [2.0, 2.5]), place("p3", [0, 3.2])];
  let seed = 401;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const actors = new OfficeActors(gate, people, spots, {maxVisitors: 3, random});
  const avatars = [...actors.agents.values()];
  const crossed = new Set();
  const dt = 1 / 30;
  for (let n = 0; n < 85 * 30 && crossed.size < people.length; n++) {
    actors.updateStatuses(people);
    actors.advance(dt);
    assert.ok(avatars.filter((a) => Math.abs(a.position[1]) < .21).length <= 1);
    avatars.forEach((a, i) => {
      if (a.position[1] > 1) crossed.add(a.id);
      for (const b of avatars.slice(i + 1)) assert.ok(distance(a.position, b.position) >= PERSONAL_SPACE);
    });
  }
  assert.equal(crossed.size, people.length);
  actors.setIdle(false);
  tickUntil(actors, () => avatars.every((a) => a.atHome && !a.trip));
  assert.equal(actors.nextWake, Infinity);
});

test("payload lặp không đặt lại chuyến đi, và bàn giao được ưu tiên", () => {
  const people = [makePerson("reviewer", [-2.3, -2])];
  const actors = new OfficeActors(gate, people, [place("break", [1.5, 2.2])], {random: () => .25});
  const avatar = actors.agents.get("reviewer");
  tickUntil(actors, () => avatar.trip && distance(avatar.home, avatar.position) > .4);
  const previous = avatar.trip;
  for (let i = 0; i < 20; i++) {
    assert.equal(actors.updateStatuses(people.map((person) => ({...person}))), false);
    actors.advance(1 / 30);
    assert.strictEqual(avatar.trip, previous);
  }
  actors.setDeliveries(new Set(["reviewer"]));
  actors.advance(1 / 30);
  assert.equal(avatar.trip.purpose, "home");
  tickUntil(actors, () => avatar.atHome);
  actors.setDeliveries(new Set());
  actors.updateStatuses([{id: "reviewer", status: "awaiting_approval"}]);
  actors.advance(60);
  assert.equal(avatar.trip, null);
  actors.updateStatuses([{id: "reviewer", status: "error"}]);
  actors.advance(60);
  assert.ok(avatar.atHome);
});

test("bàn giao qua cửa, tập tài liệu ở tay người gửi tới lúc trao; trạng thái xử lý cập nhật ngay", () => {
  const people = [makePerson("architect", [-2.3, -2], "done"), makePerson("drafter", [2, 2.6], "waiting")];
  const actors = new OfficeActors(gate, people, []);
  const [sender, receiver] = [...actors.agents.values()];
  const event = {id: 1, from: sender.id, to: receiver.id, summary: "Chương trình công năng"};
  actors.enqueue([event]);
  let crossed = false, exchanged = false, received = false;
  tickUntil(actors, () => {
    const job = actors.handoffs.get(event.id);
    if (!job) return received && sender.atHome;
    assert.equal(job.event.summary, event.summary);
    assert.ok(gate.clear(sender.position, sender.position));
    assert.ok(distance(sender.position, receiver.position) >= PERSONAL_SPACE);
    if (Math.abs(sender.position[1]) < .20) {
      assert.ok(Math.abs(sender.position[0]) < .38);
      crossed = true;
    }
    if (job.phase === "walking") {
      assert.equal(job.owner, sender);
      actors.updateStatuses([{id: receiver.id, status: "running"}]);
      assert.equal(receiver.status, "running");
      assert.equal(receiver.atHome, true);
    } else if (job.phase === "exchanging") {
      exchanged = true;
      if (job.owner === receiver) {
        received = true;
        assert.ok(receiver.sitting < .1);
        actors.updateStatuses([{id: receiver.id, status: "done"}]);
      }
    }
    return false;
  });
  assert.ok(crossed && exchanged && received);
  assert.equal(receiver.status, "done");
  assert.equal(actors.enqueue([event]), false);
  tickUntil(actors, () => sender.sitting === 1 && !sender.handoff);
});

test("trả sửa được xếp cùng hàng đợi và avatar giữ chỗ khi tạm ngừng", () => {
  const actors = new OfficeActors(gate, [makePerson("reviewer", [-2, -2]), makePerson("architect", [2, 2])], []);
  actors.setIdle(false);
  const events = [
    {id: 4, from: "reviewer", to: "architect", summary: "Mở rộng vế thang", feedback: true, pending: true},
    {id: 5, from: "architect", to: "reviewer", summary: "Bản vẽ mặt bằng v2"},
    {id: 6, from: "reviewer", to: "architect", summary: "Cần sửa chiều cao", feedback: true},
  ];
  assert.equal(actors.enqueue([events[0]]), false);
  events[0] = {...events[0], pending: false};
  assert.equal(actors.enqueue(events), true);
  actors.advance(1 / 30);
  const sender = actors.agents.get("reviewer");
  const active = actors.handoffs.get(4);
  assert.equal(active.event.feedback, true);
  const start = [...sender.position];
  actors.updateStatuses([{id: "architect", status: "running"}]);
  assert.equal(actors.enqueue(events), false);
  assert.deepEqual(sender.position, start);
  assert.strictEqual(actors.handoffs.get(4), active);
  const order = new Set();
  tickUntil(actors, () => {
    for (const job of actors.handoffs.values()) {
      if (job.phase === "exchanging" && job.owner === job.receiver) order.add(job.event.id);
    }
    return !actors.queue.length && !actors.handoffs.size;
  }, 80);
  assert.deepEqual([...order], [4, 5, 6]);
  assert.equal(actors.enqueue(events), false);
});

test("hai lượt độc lập có thể đi đồng thời, nhưng nhiều lượt đến cùng người nhận đợi đúng thứ tự", () => {
  const map = new WalkMap([]);
  const people = [makePerson("a", [-6, -3]), makePerson("b", [-6, 3]),
    makePerson("c", [6, -3]), makePerson("d", [6, 3]), makePerson("e", [0, -4])];
  const actors = new OfficeActors(map, people, []);
  actors.setIdle(false);
  actors.enqueue([{id: 1, from: "a", to: "b"}, {id: 2, from: "e", to: "b"}, {id: 3, from: "c", to: "d"}]);
  const servedAtB = new Set();
  const avatars = [...actors.agents.values()];
  let parallel = false;
  tickUntil(actors, () => {
    if (actors.handoffs.size === 2) parallel = true;
    for (const job of actors.handoffs.values()) {
      if (job.receiver?.id === "b" && job.phase === "exchanging") servedAtB.add(job.event.id);
    }
    avatars.forEach((a, i) => avatars.slice(i + 1).forEach((b) => {
      assert.ok(distance(a.position, b.position) >= PERSONAL_SPACE);
    }));
    return !actors.queue.length && !actors.handoffs.size;
  });
  assert.ok(parallel);
  assert.deepEqual([...servedAtB], [1, 2]);
});
