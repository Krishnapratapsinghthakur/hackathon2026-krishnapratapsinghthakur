"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Cpu, Sparkles, Zap } from "lucide-react";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { LinkGlow } from "@/components/ui/LinkGlow";
import { apiGet } from "@/lib/api";
import type { Health } from "@/lib/types";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
};

export default function HomePage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Health>("/health")
      .then(setHealth)
      .catch(() => setErr("API unreachable — start FastAPI on port 8000"));
  }, []);

  return (
    <div className="space-y-12 md:space-y-20">
      <section className="text-center md:text-left">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="inline-flex items-center gap-2 rounded-full border border-violet-500/30 bg-violet-500/10 px-4 py-1.5 text-xs font-medium text-violet-200"
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          Autonomous resolution mesh
        </motion.div>
        <motion.h1
          className="font-display mt-6 text-4xl font-extrabold leading-[1.1] tracking-tight text-white md:text-6xl lg:text-7xl"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05, duration: 0.55 }}
        >
          Support tickets,
          <br />
          <span className="text-gradient">resolved at lightspeed.</span>
        </motion.h1>
        <motion.p
          className="mx-auto mt-6 max-w-2xl text-lg text-slate-400 md:mx-0 md:text-xl"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.15, duration: 0.5 }}
        >
          LangGraph orchestration, smart model routing, and policy-grounded tools — unified in
          one futuristic console.
        </motion.p>
        <motion.div
          className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row md:justify-start"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.25 }}
        >
          <LinkGlow href="/tickets" className="min-w-[200px]">
            Open ticket deck
            <ArrowRight className="h-4 w-4" aria-hidden />
          </LinkGlow>
          <LinkGlow href="/compose" variant="ghost" className="min-w-[160px]">
            Quick compose
          </LinkGlow>
        </motion.div>
      </section>

      {err && (
        <p className="rounded-xl border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-center text-sm text-rose-200">
          {err}
        </p>
      )}

      {health && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap justify-center gap-2 md:justify-start"
        >
          {[
            [health.environment, "bg-emerald-500/15 text-emerald-200"],
            [health.database, "bg-cyan-500/15 text-cyan-200"],
            [health.cache === "redis" ? "redis" : "cache off", "bg-violet-500/15 text-violet-200"],
            [health.provider, "bg-fuchsia-500/15 text-fuchsia-200"],
          ].map(([label, cls]) => (
            <span
              key={String(label)}
              className={`rounded-full px-4 py-1.5 text-xs font-semibold uppercase tracking-wide ${cls}`}
            >
              {label}
            </span>
          ))}
        </motion.div>
      )}

      <motion.section
        variants={container}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
        className="grid gap-6 md:grid-cols-3"
      >
        {[
          {
            icon: Cpu,
            title: "LangGraph core",
            body: "Classify → agent loop → structured outcomes with full audit trail.",
          },
          {
            icon: Zap,
            title: "Smart routing",
            body: "Fast vs power models based on tier, tone, and order value — cost aware.",
          },
          {
            icon: Sparkles,
            title: "Glass cockpit",
            body: "Compose tickets, watch reasoning traces, and track spend in real time.",
          },
        ].map(({ icon: Icon, title, body }) => (
          <motion.div key={title} variants={item}>
            <GlassPanel className="h-full hover:ring-violet-400/30" glow>
              <Icon className="mb-4 h-8 w-8 text-cyan-300/90" aria-hidden />
              <h3 className="font-display text-lg font-bold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{body}</p>
            </GlassPanel>
          </motion.div>
        ))}
      </motion.section>
    </div>
  );
}
