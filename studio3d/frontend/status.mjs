// Một nơi duy nhất quyết định agent đang làm gì, dùng cho bảng trạng thái, nhãn 3D, luồng công việc và bảng chi tiết.
export const KINDS = {
  working: "Đang làm việc", user: "Chờ bạn", error: "Gặp lỗi", paused: "Tạm dừng",
  next: "Sắp đến lượt", queued: "Chờ đến lượt", idle: "Rảnh", off: "Đã tắt",
};
const ACTIVE_RUN = new Set(["running", "awaiting_approval", "needs_input", "paused"]);

function finished(agent, run) {
  const runs = agent.runs || agent.version || 0;
  if (agent.status === "feedback") return "Đã gửi yêu cầu sửa";
  if (agent.status === "stopped") return "Đã dừng giữa chừng";
  if (runs) return "Đã xong việc được giao" + (runs > 1 ? " · " + runs + " lần" : "");
  return run.id ? "Không tham gia lượt này" : "Chưa có lượt thiết kế";
}

export function activity(agent, run) {
  const status = agent.status;
  if (status === "skipped") return {kind: "off", label: "Đã tắt", detail: "Không dùng trong lượt này"};
  if (status === "running") return {kind: "working", label: "Đang làm việc", detail: agent.step || agent.task || ""};
  if (status === "revising") return {kind: "working", label: "Đang sửa lại", detail: agent.step || "Làm lại theo phản hồi"};
  if (status === "awaiting_approval") return {kind: "user", label: "Chờ bạn duyệt", detail: agent.step || "Đã xong, cần bạn đồng ý"};
  if (status === "needs_input") return {kind: "user", label: "Chờ bạn bổ sung", detail: "Thiếu thông tin trong yêu cầu"};
  if (status === "error") return {kind: "error", label: "Gặp lỗi", detail: agent.summary || "Xem bảng chi tiết"};
  if (status === "paused") return {kind: "paused", label: "Tạm dừng", detail: agent.step || "Lượt đang tạm dừng"};
  if (ACTIVE_RUN.has(run.status) && run.upcoming === agent.id) {
    return {kind: "next", label: "Sắp đến lượt", detail: "Làm ngay sau khi bạn duyệt"};
  }
  if (status === "waiting" && ACTIVE_RUN.has(run.status) && !agent.runs) {
    return {kind: "queued", label: "Chờ đến lượt", detail: "Chưa làm trong lượt này"};
  }
  return {kind: "idle", label: "Rảnh", detail: finished(agent, run)};
}

export function countKinds(agents, run) {
  const counts = new Map(Object.keys(KINDS).map((kind) => [kind, 0]));
  for (const agent of agents) {
    const {kind} = activity(agent, run);
    counts.set(kind, counts.get(kind) + 1);
  }
  return counts;
}

export function elapsed(since, now = Date.now()) {
  const start = Date.parse(since || "");
  if (Number.isNaN(start)) return "";
  const seconds = Math.max(0, Math.round((now - start) / 1000));
  return seconds < 60 ? seconds + " giây" : Math.floor(seconds / 60) + " phút " + seconds % 60 + " giây";
}
