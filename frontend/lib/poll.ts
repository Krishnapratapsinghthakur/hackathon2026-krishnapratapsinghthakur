import { apiGet } from "@/lib/api";
import type { TaskStatus } from "@/lib/types";

export async function pollTaskStatus(
  taskId: string,
  opts?: { maxAttempts?: number; intervalMs?: number },
): Promise<TaskStatus> {
  const max = opts?.maxAttempts ?? 90;
  const interval = opts?.intervalMs ?? 1500;
  for (let i = 0; i < max; i++) {
    const s = await apiGet<TaskStatus>(`/tickets/status/${taskId}`);
    if (s.status === "SUCCESS" || s.status === "FAILURE") return s;
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error("Task polling timed out");
}
