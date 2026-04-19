"use client";

import { motion } from "framer-motion";
import clsx from "clsx";

type Props = {
  children: React.ReactNode;
  className?: string;
  variant?: "primary" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
  onClick?: () => void;
};

export function NeonButton({
  className,
  variant = "primary",
  children,
  disabled,
  type = "button",
  onClick,
}: Props) {
  return (
    <motion.button
      type={type}
      whileHover={{ scale: disabled ? 1 : 1.02 }}
      whileTap={{ scale: disabled ? 1 : 0.98 }}
      className={clsx(
        "relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-xl px-5 py-2.5 text-sm font-semibold transition-shadow",
        variant === "primary" &&
          "bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white shadow-lg shadow-violet-900/40 hover:shadow-violet-500/25",
        variant === "ghost" &&
          "border border-white/10 bg-white/5 text-slate-200 hover:bg-white/10",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
      disabled={disabled}
      onClick={onClick}
    >
      {variant === "primary" && (
        <span className="pointer-events-none absolute inset-0 shimmer-bar opacity-30" />
      )}
      <span className="relative z-10">{children}</span>
    </motion.button>
  );
}
