"use client";

import { motion } from "framer-motion";

export function MeshBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div className="perspective-grid absolute inset-0 opacity-40" />
      <motion.div
        className="mesh-orb absolute -left-32 top-20 h-[420px] w-[420px] rounded-full bg-violet-600/25 blur-[100px]"
        aria-hidden
        initial={{ opacity: 0.4 }}
        animate={{ opacity: [0.35, 0.55, 0.35] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="mesh-orb-delay absolute -right-20 top-1/3 h-[380px] w-[380px] rounded-full bg-cyan-500/20 blur-[90px]"
        aria-hidden
        animate={{ opacity: [0.25, 0.45, 0.25] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="mesh-orb-delay-2 absolute bottom-0 left-1/3 h-[360px] w-[360px] rounded-full bg-fuchsia-600/15 blur-[100px]"
        aria-hidden
        animate={{ opacity: [0.2, 0.4, 0.2] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-slate-950/40 via-transparent to-slate-950" />
    </div>
  );
}
