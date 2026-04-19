"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import clsx from "clsx";

type Props = {
  href: string;
  children: React.ReactNode;
  variant?: "primary" | "ghost";
  className?: string;
};

export function LinkGlow({ href, children, variant = "primary", className }: Props) {
  return (
    <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} className={clsx("inline-flex", className)}>
      <Link
        href={href}
        className={clsx(
          "relative inline-flex min-w-[160px] items-center justify-center gap-2 overflow-hidden rounded-xl px-5 py-2.5 text-sm font-semibold",
          variant === "primary" &&
            "bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white shadow-lg shadow-violet-900/40",
          variant === "ghost" &&
            "border border-white/10 bg-white/5 text-slate-200 hover:bg-white/10",
        )}
      >
        {variant === "primary" && (
          <span className="pointer-events-none absolute inset-0 shimmer-bar opacity-30" />
        )}
        <span className="relative z-10 flex items-center gap-2">{children}</span>
      </Link>
    </motion.div>
  );
}
