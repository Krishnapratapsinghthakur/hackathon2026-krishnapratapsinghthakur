"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Coins, Loader2 } from "lucide-react";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { apiGet } from "@/lib/api";
import type { CostsResponse } from "@/lib/types";

export default function CostsPage() {
  const [data, setData] = useState<CostsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<CostsResponse>("/settings/costs")
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <Coins className="h-8 w-8 text-amber-300/90" aria-hidden />
        <div>
          <h1 className="font-display text-3xl font-bold text-white md:text-4xl">Cost matrix</h1>
          <p className="text-slate-400">Token usage and estimated spend per ticket</p>
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
      ) : data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Tickets", String(data.total_tickets)],
              ["Total USD", `$${data.total_cost_usd.toFixed(4)}`],
              ["Tokens", (data.total_tokens ?? 0).toLocaleString()],
              ["Avg / ticket", `$${(data.avg_cost_per_ticket ?? 0).toFixed(4)}`],
            ].map(([label, val], i) => (
              <motion.div
                key={label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <GlassPanel className="text-center">
                  <p className="font-display text-2xl font-bold text-gradient md:text-3xl">{val}</p>
                  <p className="mt-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                    {label}
                  </p>
                </GlassPanel>
              </motion.div>
            ))}
          </div>

          <GlassPanel className="overflow-x-auto p-0">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-6 py-4">Ticket</th>
                  <th className="px-4 py-4">Model</th>
                  <th className="px-4 py-4">Tier</th>
                  <th className="px-4 py-4">In</th>
                  <th className="px-4 py-4">Out</th>
                  <th className="px-6 py-4">Cost</th>
                </tr>
              </thead>
              <tbody>
                {data.per_ticket.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-14 text-center text-slate-500">
                      No cost rows yet — process tickets to populate telemetry.
                    </td>
                  </tr>
                ) : (
                  data.per_ticket.map((t, i) => (
                    <motion.tr
                      key={t.ticket_id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.02 }}
                      className="border-b border-white/5 hover:bg-white/[0.03]"
                    >
                      <td className="px-6 py-3 font-mono text-xs text-violet-300">{t.ticket_id}</td>
                      <td className="max-w-[180px] truncate px-4 py-3 text-slate-300">{t.model_used}</td>
                      <td className="px-4 py-3">
                        <span className="rounded-full bg-cyan-500/15 px-2 py-0.5 text-[10px] font-bold uppercase text-cyan-200">
                          {t.model_tier}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">
                        {t.input_tokens.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">
                        {t.output_tokens.toLocaleString()}
                      </td>
                      <td className="px-6 py-3 font-mono text-xs text-emerald-200/90">
                        ${t.estimated_cost_usd.toFixed(6)}
                      </td>
                    </motion.tr>
                  ))
                )}
              </tbody>
            </table>
          </GlassPanel>
        </>
      ) : null}
    </div>
  );
}
