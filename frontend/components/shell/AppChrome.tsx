"use client";

import { MeshBackground } from "@/components/effects/MeshBackground";
import { Scanlines } from "@/components/effects/Scanlines";
import { FloatingNav } from "@/components/shell/FloatingNav";

export function AppChrome({ children }: { children: React.ReactNode }) {
  return (
    <>
      <MeshBackground />
      <Scanlines />
      <FloatingNav />
      <div className="relative z-10 flex min-h-dvh flex-col pt-24 pb-16">
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 md:px-8">{children}</main>
        <footer className="relative z-10 mx-auto mt-12 w-full max-w-6xl px-4 text-center text-xs text-slate-500 md:px-8">
          Neural support mesh · LangGraph orchestration
        </footer>
      </div>
    </>
  );
}
