"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RangeKey } from "@/types/api";

export type Theme = "dark" | "light";

interface UIState {
  theme: Theme;
  sidebarCollapsed: boolean;
  chartRange: RangeKey;
  recent: string[];
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setChartRange: (r: RangeKey) => void;
  pushRecent: (symbol: string) => void;
  reset: () => void;
}

const defaults = {
  theme: "dark" as Theme,
  sidebarCollapsed: false,
  chartRange: "6M" as RangeKey,
  recent: [] as string[],
};

export const useUI = create<UIState>()(
  persist(
    (set) => ({
      ...defaults,
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setChartRange: (chartRange) => set({ chartRange }),
      pushRecent: (symbol) => set((s) => ({ recent: [symbol, ...s.recent.filter((x) => x !== symbol)].slice(0, 6) })),
      reset: () => set({ ...defaults }),
    }),
    { name: "mp-ui", version: 2 },
  ),
);
