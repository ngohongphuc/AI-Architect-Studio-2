import assert from "node:assert/strict";
import test from "node:test";
import { activity, countKinds, elapsed, KINDS } from "../studio3d/frontend/status.mjs";

const kind = (status, run, extra = {}) => activity({id: "a", status, ...extra}, run).kind;

test("phân biệt chờ đến lượt, sắp đến lượt và rảnh", () => {
  const running = {id: "r", status: "running"};
  assert.equal(kind("waiting", running), "queued");
  assert.equal(kind("waiting", {id: "r", status: "awaiting_approval", upcoming: "a"}), "next");
  assert.equal(kind("done", running, {runs: 1}), "idle");
  assert.equal(kind("waiting", running, {runs: 2}), "idle");
  for (const status of ["done", "stopped", "error", "not_passed"]) assert.equal(kind("waiting", {id: "r", status}), "idle");
  assert.equal(activity({id: "a", status: "waiting"}, {id: "r", status: "done"}).detail, "Không tham gia lượt này");
  assert.equal(activity({id: "a", status: "waiting"}, {id: null, status: "idle"}).detail, "Chưa có lượt thiết kế");
});

test("mỗi mã trạng thái có nhóm rõ ràng", () => {
  const run = {id: "r", status: "running"};
  const expected = {running: "working", revising: "working", awaiting_approval: "user", needs_input: "user",
    error: "error", paused: "paused", skipped: "off", done: "idle", feedback: "idle", stopped: "idle"};
  for (const [status, value] of Object.entries(expected)) {
    const result = activity({id: "a", status, runs: 1}, run);
    assert.equal(result.kind, value);
    assert.ok(KINDS[result.kind] && result.label && typeof result.detail === "string");
  }
  assert.equal(activity({id: "a", status: "revising"}, run).label, "Đang sửa lại");
});

test("đếm theo nhóm và thời gian đang làm", () => {
  const counts = countKinds([{id: "a", status: "running"}, {id: "b", status: "waiting"}, {id: "c", status: "done", runs: 1}],
    {id: "r", status: "running"});
  assert.deepEqual([counts.get("working"), counts.get("queued"), counts.get("idle"), counts.get("error")], [1, 1, 1, 0]);
  const now = Date.parse("2026-11-25T10:01:05+00:00");
  assert.equal(elapsed("2026-11-25T10:01:00+00:00", now), "5 giây");
  assert.equal(elapsed("2026-11-25T10:00:00+00:00", now), "1 phút 5 giây");
  assert.equal(elapsed(null, now), "");
});
