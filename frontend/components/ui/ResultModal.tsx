"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type { TicketResult } from "@/lib/types";
import { NeonButton } from "./NeonButton";
import { ToolCallTimeline } from "./ToolCallTimeline";

export function ResultModal({
  open,
  onClose,
  result,
}: {
  open: boolean;
  onClose: () => void;
  result: TicketResult | null;
}) {
  return (
    <AnimatePresence>
      {open && result && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
            aria-label="Close modal"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            className="glass-panel relative z-10 max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl p-6 shadow-2xl ring-1 ring-violet-500/30"
            initial={{ scale: 0.94, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.94, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
          >
            <button
              type="button"
              onClick={onClose}
              className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 hover:bg-white/10 hover:text-white"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
            <div className="mb-4 flex flex-wrap items-center gap-3 pr-10">
              <h2 className="text-lg font-bold tracking-tight text-white md:text-xl">
                {result.ticket_id}
              </h2>
              <span
                className={`rounded-full px-3 py-0.5 text-xs font-bold uppercase tracking-wide ${
                  result.status === "resolved"
                    ? "bg-emerald-500/20 text-emerald-300"
                    : result.status === "escalated"
                      ? "bg-amber-500/20 text-amber-200"
                      : result.status === "failed"
                        ? "bg-rose-500/20 text-rose-300"
                        : "bg-slate-500/20 text-slate-300"
                }`}
              >
                {result.status}
              </span>
            </div>
            {result.response && (
              <p className="mb-6 whitespace-pre-wrap rounded-xl bg-slate-900/60 p-4 text-sm leading-relaxed text-slate-200 ring-1 ring-white/5">
                {result.response}
              </p>
            )}
            {result.escalation_summary && (
              <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-100">
                {result.escalation_summary}
              </div>
            )}
            {result.tool_calls && result.tool_calls.length > 0 && (
              <div className="mb-6">
                <ToolCallTimeline tools={result.tool_calls} />
              </div>
            )}
            <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
              {[
                ["Category", result.category ?? "—"],
                ["Priority", result.priority ?? "—"],
                [
                  "Confidence",
                  result.confidence != null
                    ? `${(result.confidence * 100).toFixed(0)}%`
                    : "—",
                ],
                ["Tool calls", String(result.tool_calls_count ?? result.tool_calls?.length ?? 0)],
                ["Model", result.model_used ?? "—"],
                ["Tier", result.model_tier ?? "—"],
              ].map(([k, v]) => (
                <div key={k} className="rounded-lg bg-slate-900/50 p-3 ring-1 ring-white/5">
                  <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    {k}
                  </dt>
                  <dd className="mt-1 font-semibold text-slate-100">{v}</dd>
                </div>
              ))}
            </dl>
            {result.reasoning_steps && result.reasoning_steps.length > 0 && (
              <div className="mt-6">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Reasoning trace
                </p>
                <ul className="space-y-2 text-sm text-slate-400">
                  {result.reasoning_steps.map((s, i) => (
                    <li key={i} className="flex gap-2 border-b border-white/5 pb-2 last:border-0">
                      <span className="text-violet-400">→</span>
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-6 flex justify-end">
              <NeonButton variant="ghost" type="button" onClick={onClose}>
                Close
              </NeonButton>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
