"use client";

import { Bell, Menu, Moon, Search, Sun } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { useNotifications } from "@/hooks/useNotifications";
import { useUI } from "@/stores/ui";
import { fmtDay } from "@/lib/utils";
import { useHydrated } from "@/hooks/useHydrated";
import { Badge } from "@/components/ui/primitives";

export function Topbar({ onMenu, onSearch }: { onMenu: () => void; onSearch: () => void }) {
  const hydrated = useHydrated();
  const theme = useUI((s) => s.theme);
  const toggleTheme = useUI((s) => s.toggleTheme);
  const [bell, setBell] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const notes = useNotifications();
  const live = useLiveEvents();
  const unread = notes.data?.unread ?? 0;
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

        <span
          title={live === "live" ? "Receiving live updates from the server" : live === "polling" ? "Live stream unavailable; refreshing by polling" : "Connecting to live updates"}
          className="hidden items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-[11px] text-muted sm:inline-flex"
        >
          <span className={`h-1.5 w-1.5 rounded-full ${live === "live" ? "bg-up" : live === "polling" ? "bg-warn" : "bg-muted animate-pulse"}`} aria-hidden />
          {live === "live" ? "Live" : live === "polling" ? "Polling" : "Connecting"}
        </span>
        <div className="relative" ref={bellRef}>
          <button onClick={() => setBell((v) => !v)} aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} aria-expanded={bell} className={`${btn} relative`}>
            <Bell className="h-4 w-4" />
            {unread > 0 && (
              <span className="num absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-semibold text-white">{unread > 9 ? "9+" : unread}</span>
            )}
          </button>
          {bell && (
            <div className="absolute right-0 top-11 w-80 animate-pop rounded-xl border border-border bg-surface p-3 shadow-2xl">
              <div className="flex items-center justify-between px-1 pb-2">
                <p className="text-sm font-medium">Alert notifications</p>
                {unread > 0 && <button onClick={() => notes.markRead.mutate(null)} className="text-xs text-accent hover:underline">Mark all read</button>}
              </div>
              {notes.isError ? (
                <p className="px-1 py-3 text-xs text-muted">Could not load notifications.</p>
              ) : !notes.data || notes.data.items.length === 0 ? (
                <p className="px-1 py-3 text-xs text-muted">No alerts have fired yet. <Link href="/alerts" onClick={() => setBell(false)} className="text-accent hover:underline">Create one</Link>.</p>
              ) : (
                <ul className="max-h-80 space-y-1 overflow-y-auto">
                  {notes.data.items.slice(0, 8).map((n) => (
                    <li key={n.id} className={`rounded-lg px-2 py-2 text-xs ${n.read ? "text-muted" : "bg-accent/10"}`}>
                      <Link href={`/markets/${n.symbol}`} onClick={() => setBell(false)} className="font-semibold hover:text-accent">{n.symbol}</Link>
                      <span className="ml-1.5 text-[10.5px] text-muted">session {fmtDay(n.observed_day)}</span>
                      <p className="mt-0.5">{n.message}</p>
                    </li>
                  ))}
                </ul>
              )}
              <Link href="/alerts" onClick={() => setBell(false)} className="mt-2 block rounded-lg px-1 py-1.5 text-center text-xs text-muted hover:text-fg">Manage alerts</Link>
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
