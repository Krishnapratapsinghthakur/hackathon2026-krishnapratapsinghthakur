"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Layers } from "lucide-react";
import { NeonButton } from "@/components/ui/NeonButton";
import { ResultModal } from "@/components/ui/ResultModal";
import { apiGet, apiPost } from "@/lib/api";
import { pollTaskStatus } from "@/lib/poll";
import type { AsyncQueued, TicketInput, TicketResult } from "@/lib/types";

function isAsyncQueued(x: unknown): x is AsyncQueued {
  return (
    typeof x === "object" &&
    x !== null &&
    "mode" in x &&
    (x as AsyncQueued).mode === "async" &&
    "task_id" in x
  );
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState<TicketInput[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState<string | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<TicketResult | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    apiGet<TicketInput[]>("/tickets/sample")
      .then(setTickets)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function resolveProcessResponse(raw: unknown): Promise<TicketResult> {
    if (isAsyncQueued(raw)) {
      const done = await pollTaskStatus(raw.task_id);
      if (done.status === "FAILURE") {
        throw new Error(done.error || "Background task failed");
      }
      return done.result as TicketResult;
    }
    return raw as TicketResult;
  }

  async function runOne(t: TicketInput) {
    setProcessing(t.ticket_id);
    setError(null);
    try {
      const raw = await apiPost<unknown>("/tickets/process", t);
      const result = await resolveProcessResponse(raw);
      setModal(result);
      setModalOpen(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setProcessing(null);
    }
  }

  async function runBatch() {
    setBatchBusy(true);
    setError(null);
    try {
      const batch = await apiPost<{ results: TicketResult[] }>("/tickets/batch", {
        load_sample: true,
      });
      const last = batch.results[batch.results.length - 1];
      if (last) {
        setModal(last);
        setModalOpen(true);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Batch failed");
    } finally {
      setBatchBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold text-white md:text-4xl">Ticket deck</h1>
          <p className="mt-2 text-slate-400">Sample queue · tap a card to run the neural pipeline</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <NeonButton variant="ghost" type="button" onClick={load} disabled={loading}>
            Refresh
          </NeonButton>
          <NeonButton type="button" onClick={runBatch} disabled={batchBusy || loading}>
            {batchBusy ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Processing…
              </>
            ) : (
              <>
                <Layers className="h-4 w-4" />
                Process all
              </>
            )}
          </NeonButton>
        </div>
      </div>

      {error && (
        <p className="rounded-xl border border-rose-500/40 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
          {error}
        </p>
      )}

      {loading ? (
        <div className="flex justify-center py-24">
          <Loader2 className="h-10 w-10 animate-spin text-violet-400" aria-label="Loading" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence>
            {tickets.map((t, i) => {
              const busy = processing === t.ticket_id;
              const disabled = !!processing;
              return (
                <motion.div
                  key={t.ticket_id}
                  layout
                  role="button"
                  tabIndex={disabled ? -1 : 0}
                  aria-disabled={disabled}
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ delay: i * 0.03 }}
                  whileHover={disabled || busy ? undefined : { scale: 1.02 }}
                  whileTap={disabled || busy ? undefined : { scale: 0.99 }}
                  onClick={() => {
                    if (!disabled) void runOne(t);
                  }}
                  onKeyDown={(e) => {
                    if (disabled) return;
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      void runOne(t);
                    }
                  }}
                  className={`glass-panel relative h-full cursor-pointer rounded-2xl p-6 text-left transition-shadow ${
                    busy ? "ring-2 ring-cyan-400/50" : "hover:ring-1 hover:ring-violet-400/40"
                  } ${disabled && !busy ? "cursor-not-allowed opacity-60" : ""}`}
                >
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
                  <p className="text-xs font-semibold tracking-wide text-violet-300/90">{t.ticket_id}</p>
                  <p className="mt-2 font-semibold text-slate-100">{t.subject}</p>
                  <p className="mt-2 line-clamp-2 text-sm text-slate-500">{t.body}</p>
                  <div className="mt-4 flex items-center justify-between border-t border-white/5 pt-3 text-xs text-slate-500">
                    <span className="truncate pr-2">{t.customer_email}</span>
                    <span className="shrink-0 rounded-full bg-white/5 px-2 py-0.5 font-mono text-[10px] text-cyan-200/90">
                      T{t.tier ?? 1}
                    </span>
                  </div>
                  {busy && (
                    <div className="absolute right-4 top-4">
                      <Loader2 className="h-5 w-5 animate-spin text-cyan-300" aria-hidden />
                    </div>
                  )}
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      <ResultModal open={modalOpen} onClose={() => setModalOpen(false)} result={modal} />
    </div>
  );
}
