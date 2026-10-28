"use client";

import { Moon, Sun } from "lucide-react";
import { Card, CardHeader, PageHeader } from "@/components/ui/primitives";
import { RANGES } from "@/components/dashboard/MarketChartCard";
import { cn } from "@/lib/utils";
import { useHydrated } from "@/hooks/useHydrated";
import { useUI } from "@/stores/ui";

export default function SettingsPage() {
  const hydrated = useHydrated();
  const { theme, setTheme, chartRange, setChartRange, sidebarCollapsed, toggleSidebar, favorites, reset } = useUI();
  const seg = (on: boolean) => cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors", on ? "border-accent bg-accent/10 text-fg" : "border-border text-muted hover:text-fg");
  if (!hydrated) return <PageHeader title="Settings" />;

  return (
    <>
      <PageHeader title="Settings" description="Preferences are stored in this browser. Account-level sync arrives with authentication." />
      <div className="grid max-w-3xl gap-5">
        <Card>
          <CardHeader title="Appearance" />
          <div className="flex gap-3 px-4 pb-4">
            <button className={seg(theme === "dark")} aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Moon className="h-4 w-4" /> Dark</button>
            <button className={seg(theme === "light")} aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Sun className="h-4 w-4" /> Light</button>
          </div>
        </Card>
        <Card>
          <CardHeader title="Charts" subtitle="Default date range for price charts" />
          <div className="flex flex-wrap gap-2 px-4 pb-4">
            {RANGES.map((r) => (
              <button key={r} className={seg(chartRange === r)} aria-pressed={chartRange === r} onClick={() => setChartRange(r)}>{r}</button>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Layout" />
          <div className="flex items-center justify-between px-4 pb-4 text-sm">
            <span>Collapse the sidebar by default</span>
            <button role="switch" aria-checked={sidebarCollapsed} onClick={toggleSidebar} className={cn("h-6 w-11 rounded-full border border-border p-0.5 transition-colors", sidebarCollapsed ? "bg-accent" : "bg-elevated")}>
              <span className={cn("block h-[18px] w-[18px] rounded-full bg-white transition-transform", sidebarCollapsed && "translate-x-5")} />
            </button>
          </div>
        </Card>
        <Card>
          <CardHeader title="Saved data" subtitle={`${favorites.length} favorite symbols stored locally`} />
          <div className="px-4 pb-4">
            <button onClick={reset} className="rounded-lg border border-down/40 px-3 py-2 text-sm font-medium text-down hover:bg-down/10">Reset all preferences</button>
          </div>
        </Card>
      </div>
    </>
  );
}
