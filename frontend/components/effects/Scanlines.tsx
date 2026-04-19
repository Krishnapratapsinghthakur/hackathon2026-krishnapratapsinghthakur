"use client";

export function Scanlines() {
  return (
    <div
      className="pointer-events-none fixed inset-0 z-[5] opacity-[0.03]"
      style={{
        backgroundImage:
          "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.15) 2px, rgba(255,255,255,0.15) 3px)",
      }}
      aria-hidden
    />
  );
}
