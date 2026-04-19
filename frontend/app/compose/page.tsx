"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Send, Sparkles } from "lucide-react";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { NeonButton } from "@/components/ui/NeonButton";
import { ResultModal } from "@/components/ui/ResultModal";
import { apiPost } from "@/lib/api";
import { pollTaskStatus } from "@/lib/poll";
import type { AsyncQueued, TicketResult } from "@/lib/types";

const chips = [
  "alice.turner@email.com",
  "bob.mendes@email.com",
  "carol.nguyen@email.com",
  "david.park@email.com",
];

function isAsyncQueued(x: unknown): x is AsyncQueued {
  return (
    typeof x === "object" &&
    x !== null &&
    "mode" in x &&
    (x as AsyncQueued).mode === "async" &&
    "task_id" in x
  );
}

export default function ComposePage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<TicketResult | null>(null);
  const [open, setOpen] = useState(false);

  async function submit() {
    if (!email.trim() || !message.trim()) {
      setError("Email and message are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let raw = await apiPost<unknown>("/tickets/quick", {
        customer_email: email.trim(),
        message: message.trim(),
      });
      if (isAsyncQueued(raw)) {
        const done = await pollTaskStatus(raw.task_id);
        if (done.status === "FAILURE") throw new Error(done.error || "Task failed");
        raw = done.result;
      }
      setModal(raw as TicketResult);
      setOpen(true);
      setMessage("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="font-display text-3xl font-bold text-white md:text-4xl">Quick compose</h1>
        <p className="mt-2 text-slate-400">Minimal payload — ticket id and subject are synthesized.</p>
      </div>

      <GlassPanel glow>
        <div className="mb-6 flex items-center gap-2 text-violet-200/90">
          <Sparkles className="h-5 w-5" aria-hidden />
          <span className="text-sm font-medium">Neural intake</span>
        </div>
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
          Customer email
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-slate-100 outline-none ring-cyan-400/40 transition focus:border-cyan-400/50 focus:ring-2"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {chips.map((c) => (
            <motion.button
              key={c}
              type="button"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => setEmail(c)}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-400 hover:border-violet-400/40 hover:text-slate-200"
            >
              {c.split("@")[0]}
            </motion.button>
          ))}
        </div>

        <label className="mt-8 block text-xs font-semibold uppercase tracking-wider text-slate-500">
          Message
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Describe the issue, include order id if you have one…"
          rows={6}
          className="mt-2 w-full resize-y rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3 text-slate-100 outline-none ring-cyan-400/40 transition focus:border-cyan-400/50 focus:ring-2"
        />

        {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}

        <div className="mt-8 flex justify-end">
          <NeonButton type="button" onClick={() => void submit()} disabled={busy}>
            {busy ? "Transmitting…" : (
              <>
                <Send className="h-4 w-4" aria-hidden />
                Dispatch ticket
              </>
            )}
          </NeonButton>
        </div>
      </GlassPanel>

      <ResultModal open={open} onClose={() => setOpen(false)} result={modal} />
    </div>
  );
}
