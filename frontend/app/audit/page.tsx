"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, ScrollText } from "lucide-react";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { ToolCallTimeline } from "@/components/ui/ToolCallTimeline";
import { apiGet } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<AuditEntry | null>(null);

  useEffect(() => {
    apiGet<AuditEntry[]>("/audit")
      .then(setRows)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function openRow(ticketId: string) {
    try {
      const d = await apiGet<AuditEntry>(`/audit/${ticketId}`);
      setDetail(d);
    } catch {
      setError("Failed to load audit detail");
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <ScrollText className="h-8 w-8 text-cyan-300/80" aria-hidden />
        <div>
          <h1 className="font-display text-3xl font-bold text-white md:text-4xl">Audit trail</h1>
          <p className="text-slate-400">Immutable log of processed tickets</p>
        </div>
      </div>

      {error && (
        <p className="rounded-xl border border-rose-500/40 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
          {error}
        </p>
      )}

      {loading ? (
        <div className="flex justify-center py-24">
          <Loader2 className="h-10 w-10 animate-spin text-violet-400" aria-hidden />
        </div>
      ) : (
        <GlassPanel className="overflow-x-auto p-0">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-slate-500">
                <th className="px-6 py-4">Ticket</th>
                <th className="px-4 py-4">Status</th>
                <th className="px-4 py-4">Category</th>
                <th className="px-4 py-4">Priority</th>
                <th className="px-4 py-4">Confidence</th>
                <th className="px-6 py-4">Tools</th>
              </tr>
            </thead>
            <tbody>
              <AnimatePresence>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-16 text-center text-slate-500">
                      No audit rows yet — process tickets from the deck first.
                    </td>
                  </tr>
                ) : (
                  rows.map((r, i) => (
                    <motion.tr
                      key={r.ticket_id}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.02 }}
                      className="cursor-pointer border-b border-white/5 hover:bg-white/[0.04]"
                      onClick={() => void openRow(r.ticket_id)}
                    >
                      <td className="px-6 py-3 font-mono text-xs font-semibold text-violet-300">
                        {r.ticket_id}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                            r.status === "resolved"
                              ? "bg-emerald-500/20 text-emerald-200"
                              : r.status === "failed"
                                ? "bg-rose-500/20 text-rose-200"
                                : "bg-amber-500/15 text-amber-100"
                          }`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{r.category ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-400">{r.priority ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-400">
                        {r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td className="px-6 py-3 text-slate-400">{r.tool_calls?.length ?? 0}</td>
                    </motion.tr>
                  ))
                )}
              </AnimatePresence>
            </tbody>
          </table>
        </GlassPanel>
      )}

      <AnimatePresence>
        {detail && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[90] flex items-center justify-center p-4"
          >
            <button
              type="button"
              className="absolute inset-0 bg-slate-950/85 backdrop-blur-sm"
              aria-label="Close"
              onClick={() => setDetail(null)}
            />
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="glass-panel relative z-10 max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-2xl p-6"
            >
              <h2 className="font-display text-xl font-bold text-white">{detail.ticket_id}</h2>
              {detail.tool_calls && detail.tool_calls.length > 0 && (
                <div className="mt-4">
                  <ToolCallTimeline tools={detail.tool_calls} />
                </div>
              )}
              {detail.final_response && (
                <p className="mt-4 whitespace-pre-wrap rounded-xl bg-slate-900/50 p-4 text-sm text-slate-300">
                  {detail.final_response}
                </p>
              )}
              {detail.reasoning && detail.reasoning.length > 0 && (
                <ul className="mt-4 space-y-2 text-sm text-slate-400">
                  {detail.reasoning.map((s, i) => (
                    <li key={i} className="flex gap-2 border-b border-white/5 pb-2">
                      <span className="text-violet-400">→</span>
                      {s}
                    </li>
                  ))}
                </ul>
              )}
              <button
                type="button"
                onClick={() => setDetail(null)}
                className="mt-6 text-sm font-medium text-cyan-300 hover:underline"
              >
                Close
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
