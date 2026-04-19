"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import type { ToolCallEntry } from "@/lib/types";
import clsx from "clsx";

function prettyJson(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      return JSON.stringify(parsed, null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function ToolCallTimeline({ tools }: { tools: ToolCallEntry[] }) {
  const [open, setOpen] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(tools.map((_, i) => [i, i === 0])),
  );

  if (!tools.length) {
    return (
      <p className="rounded-xl border border-white/10 bg-slate-900/40 px-4 py-3 text-sm text-slate-500">
        No tool invocations recorded for this run.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
        <Wrench className="h-3.5 w-3.5 text-cyan-400/80" aria-hidden />
        Tool trace — inputs and outputs
      </div>
      <ol className="relative space-y-3 border-l border-violet-500/25 pl-5">
        {tools.map((tc, i) => {
          const expanded = open[i] ?? false;
          return (
            <li key={`${tc.tool_name}-${i}`} className="relative">
              <span className="absolute -left-[21px] top-3 h-2.5 w-2.5 rounded-full border-2 border-violet-400/60 bg-slate-950" />
              <motion.div
                layout
                className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/50 ring-1 ring-white/[0.04]"
              >
                <button
                  type="button"
                  onClick={() => setOpen((s) => ({ ...s, [i]: !expanded }))}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-white/[0.04]"
                >
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-sm font-semibold text-violet-200">{tc.tool_name}</span>
                    {tc.why && (
                      <p className="mt-1 text-xs leading-relaxed text-slate-400">{tc.why}</p>
                    )}
                  </div>
                  {expanded ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" aria-hidden />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" aria-hidden />
                  )}
                </button>
                <AnimatePresence initial={false}>
                  {expanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="border-t border-white/5"
                    >
                      <div className="grid gap-3 p-4 md:grid-cols-2">
                        <div>
                          <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                            Input (arguments)
                          </p>
                          <pre className="max-h-48 overflow-auto rounded-lg bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-emerald-200/90 ring-1 ring-white/5">
                            {prettyJson(tc.arguments ?? {})}
                          </pre>
                        </div>
                        <div>
                          <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                            Output (result)
                          </p>
                          <pre
                            className={clsx(
                              "max-h-48 overflow-auto rounded-lg p-3 font-mono text-[11px] leading-relaxed ring-1 ring-white/5",
                              tc.error
                                ? "bg-rose-950/40 text-rose-200"
                                : "bg-black/40 text-sky-200/90",
                            )}
                          >
                            {tc.error ? `Error: ${tc.error}` : prettyJson(tc.result)}
                          </pre>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
