"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, X } from "lucide-react";
import { BRAND_ICON, NAV } from "@/lib/nav";
import { progress } from "@/lib/roadmap";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";
import { useHydrated } from "@/hooks/useHydrated";
import { ProgressBar } from "@/components/ui/primitives";

const GROUPS = ["Overview", "Analysis", "Tools", "System"] as const;

export function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const hydrated = useHydrated();
  const collapsedPref = useUI((s) => s.sidebarCollapsed);
  const toggle = useUI((s) => s.toggleSidebar);
  const collapsed = hydrated && collapsedPref;
  const prog = progress();

  const body = (isMobile: boolean) => {
    const slim = collapsed && !isMobile;
    return (
      <div className="flex h-full flex-col">
        <div className={cn("flex h-16 items-center gap-3 border-b border-border px-4", slim && "justify-center px-0")}>
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-accent to-teal text-white shadow-lg shadow-accent/20">
            <BRAND_ICON className="h-5 w-5" aria-hidden />
          </div>
          {!slim && (
            <div className="min-w-0 leading-tight">
              <div className="text-[15px] font-semibold tracking-tight">MarketPulse</div>
              <div className="truncate text-[10.5px] text-muted">Market intelligence, engineered.</div>
            </div>
          )}
          {isMobile && (
            <button onClick={onClose} aria-label="Close navigation" className="ml-auto rounded-md p-1.5 text-muted hover:bg-elevated">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2.5 py-4">
          {GROUPS.map((g) => (
            <div key={g} className="mb-4">
              {!slim && <div className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted/70">{g}</div>}
              <ul className="space-y-0.5">
                {NAV.filter((n) => n.group === g).map((n) => {
                  const active = pathname === n.href || pathname.startsWith(`${n.href}/`);
                  const planned = n.part > prog.done;
                  return (
                    <li key={n.href}>
                      <Link
                        href={n.href}
                        onClick={onClose}
                        title={slim ? n.label : undefined}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "group relative flex items-center gap-3 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                          slim && "justify-center",
                          active ? "bg-accent/12 text-fg" : "text-muted hover:bg-elevated hover:text-fg",
                        )}
                      >
                        {active && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-accent" />}
                        <n.icon className={cn("h-[18px] w-[18px] shrink-0", active && "text-accent")} aria-hidden />
                        {!slim && <span className="flex-1 truncate">{n.label}</span>}
                        {!slim && planned && <span className="rounded bg-elevated px-1.5 py-0.5 text-[9.5px] font-semibold text-muted">P{n.part}</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {!slim && (
          <div className="mx-3 mb-3 rounded-xl border border-border bg-elevated/60 p-3">
            <div className="mb-2 flex items-center justify-between text-[11px]">
              <span className="font-medium">Build progress</span>
              <span className="num text-muted">{prog.done}/{prog.total} parts</span>
            </div>
            <ProgressBar value={prog.pct} />
          </div>
        )}

        {!isMobile && (
          <button
            onClick={toggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="m-3 mt-0 flex items-center justify-center gap-2 rounded-lg border border-border py-2 text-xs text-muted hover:bg-elevated hover:text-fg"
          >
            <ChevronsLeft className={cn("h-4 w-4 transition-transform duration-300", collapsed && "rotate-180")} aria-hidden />
            {!collapsed && "Collapse"}
          </button>
        )}
      </div>
    );
  };

  return (
    <>
      <aside
        className={cn(
          "sticky top-0 hidden h-screen shrink-0 border-r border-border bg-surface/80 backdrop-blur transition-[width] duration-300 ease-out lg:block",
          collapsed ? "w-[68px]" : "w-64",
        )}
      >
        {body(false)}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/60" onClick={onClose} />
          <aside className="absolute inset-y-0 left-0 w-72 animate-pop border-r border-border bg-surface">{body(true)}</aside>
        </div>
      )}
    </>
  );
}
