"use client";

import { useQuery } from "@tanstack/react-query";
import { CornerDownLeft, MoonStar, PanelLeft, Search, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { api } from "@/lib/api";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";

interface Item {
  id: string;
  group: "Pages" | "Stocks" | "Actions";
  label: string;
  hint?: string;
  icon: ComponentType<{ className?: string }>;
  run: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const { toggleTheme, toggleSidebar, pushRecent, recent } = useUI();

  const stocks = useQuery({ queryKey: ["stocks"], queryFn: api.stocks, enabled: open, staleTime: 60_000 });

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const go = (href: string) => () => {
      router.push(href);
      onClose();
    };
    const pages: Item[] = NAV.map((n) => ({ id: `p-${n.href}`, group: "Pages", label: n.label, hint: n.href, icon: n.icon, run: go(n.href) }));
    const syms: Item[] = (stocks.data?.items ?? []).map((s) => ({
      id: `s-${s.symbol}`,
      group: "Stocks",
      label: `${s.symbol} — ${s.name}`,
      hint: s.exchange,
      icon: TrendingUp,
      run: () => {
        pushRecent(s.symbol);
        go(`/markets/${s.symbol}`)();
      },
    }));
    const actions: Item[] = [
      { id: "a-theme", group: "Actions", label: "Switch theme", hint: "dark / light", icon: MoonStar, run: () => { toggleTheme(); onClose(); } },
      { id: "a-sidebar", group: "Actions", label: "Toggle sidebar", icon: PanelLeft, run: () => { toggleSidebar(); onClose(); } },
    ];
    const term = q.trim().toLowerCase();
    const all = [...pages, ...syms, ...actions];
    if (!term) {
      // Empty query: recently viewed symbols first, then pages and actions.
      const rec = recent.map((r) => syms.find((s) => s.id === `s-${r}`)).filter(Boolean) as Item[];
      return [...rec, ...pages, ...actions];
    }
    return all.filter((i) => i.label.toLowerCase().includes(term) || i.hint?.toLowerCase().includes(term));
  }, [q, stocks.data, recent, router, onClose, toggleTheme, toggleSidebar, pushRecent]);

  useEffect(() => setActive(0), [q]);

  if (!open) return null;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); items[active]?.run(); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
    else if (e.key === "Tab") { e.preventDefault(); inputRef.current?.focus(); } // keep focus inside dialog
  };

  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKey}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative w-full max-w-xl animate-pop overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="h-4 w-4 text-muted" aria-hidden />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search symbols, pages, actions…"
            aria-label="Search commands"
            aria-controls="cmd-list"
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
          />
          <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted">ESC</kbd>
        </div>
        <ul id="cmd-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
          {stocks.isLoading && q && <li className="px-3 py-2 text-xs text-muted">Loading symbols…</li>}
          {items.length === 0 && !stocks.isLoading && <li className="px-3 py-8 text-center text-sm text-muted">No results for “{q}”.</li>}
          {items.map((it, i) => {
            const header = it.group !== lastGroup ? it.group : null;
            lastGroup = it.group;
            return (
              <li key={it.id} role="presentation">
                {header && <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted/70">{header}</div>}
                <button
                  role="option"
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
                  onClick={it.run}
                  className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm", i === active ? "bg-accent/12 text-fg" : "text-muted")}
                >
                  <it.icon className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="flex-1 truncate">{it.label}</span>
                  {it.hint && <span className="text-[11px] text-muted">{it.hint}</span>}
                  {i === active && <CornerDownLeft className="h-3.5 w-3.5" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
