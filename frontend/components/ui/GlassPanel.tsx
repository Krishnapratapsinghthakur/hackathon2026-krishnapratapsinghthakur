"use client";

import { motion } from "framer-motion";
import clsx from "clsx";

type Props = {
  className?: string;
  glow?: boolean;
  children: React.ReactNode;
};

export function GlassPanel({ className, glow, children }: Props) {
  return (
    <motion.div
      className={clsx(
        "glass-panel relative overflow-hidden rounded-2xl p-6 md:p-8",
        glow && "ring-1 ring-violet-500/20",
        className,
      )}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />
      {children}
    </motion.div>
  );
}
