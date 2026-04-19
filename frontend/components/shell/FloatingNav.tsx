"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Orbit, Layers, PenLine, ScrollText, Coins, Home } from "lucide-react";
import clsx from "clsx";

const links = [
  { href: "/", label: "Home", icon: Home },
  { href: "/tickets", label: "Tickets", icon: Layers },
  { href: "/compose", label: "Compose", icon: PenLine },
  { href: "/audit", label: "Audit", icon: ScrollText },
  { href: "/costs", label: "Costs", icon: Coins },
] as const;

export function FloatingNav() {
  const pathname = usePathname();

  return (
    <header className="fixed left-0 right-0 top-0 z-50 flex justify-center px-3 pt-4 md:px-6">
      <motion.nav
        initial={{ y: -24, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: "spring", stiffness: 120, damping: 18 }}
        className="glass-panel flex max-w-full items-center gap-1 rounded-full px-2 py-2 md:gap-2 md:px-3"
      >
        <div className="flex items-center gap-2 pr-2 md:pr-4 md:pl-2">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-cyan-400 p-[1px]">
            <div className="flex h-full w-full items-center justify-center rounded-full bg-slate-950">
              <Orbit className="h-4 w-4 text-cyan-300" aria-hidden />
            </div>
          </div>
          <span className="hidden font-semibold tracking-tight text-slate-100 sm:inline md:text-sm">
            Shop<span className="text-gradient">Wave</span>
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-0.5 sm:gap-1">
          {links.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link key={href} href={href}>
                <span
                  className={clsx(
                    "relative flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-medium transition-colors md:text-sm",
                    active
                      ? "text-white"
                      : "text-slate-400 hover:text-slate-200",
                  )}
                >
                  {active && (
                    <motion.span
                      layoutId="nav-pill"
                      className="absolute inset-0 rounded-full bg-white/10 ring-1 ring-violet-400/40"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <Icon className="relative z-10 h-3.5 w-3.5 md:h-4 md:w-4" aria-hidden />
                  <span className="relative z-10 hidden sm:inline">{label}</span>
                </span>
              </Link>
            );
          })}
        </div>
      </motion.nav>
    </header>
  );
}
