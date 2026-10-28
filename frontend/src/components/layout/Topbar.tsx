"use client";

import { Bell, Menu, Moon, Search, Sun } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useUI } from "@/stores/ui";
import { useHydrated } from "@/hooks/useHydrated";
import { Badge } from "@/components/ui/primitives";

export function Topbar({ onMenu, onSearch }: { onMenu: () => void; onSearch: () => void }) {
  const hydrated = useHydrated();
  const theme = useUI((s) => s.theme);
  const toggleTheme = useUI((s) => s.toggleTheme);
  const [bell, setBell] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const isDark = !hydrated || theme === "dark";

  useEffect(() => {
    if (!bell) return;
    const close = (e: MouseEvent) => !bellRef.current?.contains(e.target as Node) && setBell(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setBell(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [bell]);

  const btn = "grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface text-muted transition-colors hover:border-accent/50 hover:text-fg";

  return (
    <div className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-bg/80 px-4 backdrop-blur-md md:px-6">
      <button onClick={onMenu} aria-label="Open navigation" className={`${btn} lg:hidden`}>
        <Menu className="h-4 w-4" />
      </button>

      <button
        onClick={onSearch}
        aria-label="Search symbols and commands"
        className="flex h-9 w-full max-w-md items-center gap-2.5 rounded-lg border border-border bg-surface px-3 text-sm text-muted transition-colors hover:border-accent/50"
      >
        <Search className="h-4 w-4" aria-hidden />
        <span className="flex-1 truncate text-left">Search symbols…</span>
        <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-[10px] sm:inline">Ctrl K</kbd>
      </button>

      <div className="ml-auto flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 md:flex" aria-label="Market data status">
          <span className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-warn" aria-hidden />
          <span className="text-xs text-muted">Demo data</span>
          <Badge tone="warn">Simulated</Badge>
        </div>

        <div className="relative" ref={bellRef}>
          <button onClick={() => setBell((v) => !v)} aria-label="Notifications" aria-expanded={bell} className={btn}>
            <Bell className="h-4 w-4" />
          </button>
          {bell && (
            <div className="absolute right-0 top-11 w-72 animate-pop rounded-xl border border-border bg-surface p-4 shadow-2xl">
              <p className="text-sm font-medium">Notifications</p>
              <p className="mt-1 text-xs text-muted">
                Nothing yet. Alert and pipeline notifications will appear here once the alert engine ships (Part 5).
              </p>
            </div>
          )}
        </div>

        <button onClick={toggleTheme} aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"} className={btn}>
          {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        <Link href="/settings" aria-label="Settings" className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-accent to-teal text-xs font-semibold text-white">
          MP
        </Link>
      </div>
    </div>
  );
}
