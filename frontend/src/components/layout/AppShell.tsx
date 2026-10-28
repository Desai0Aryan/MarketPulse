"use client";

import { useCallback, useEffect, useState } from "react";
import { useUI } from "@/stores/ui";
import { CommandPalette } from "./CommandPalette";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileNav, setMobileNav] = useState(false);
  const [palette, setPalette] = useState(false);
  const theme = useUI((s) => s.theme);

  // Apply theme to <html>; the inline script in layout.tsx prevents a flash on first paint.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const closePalette = useCallback(() => setPalette(false), []);

  return (
    <div className="flex min-h-screen">
      <Sidebar mobileOpen={mobileNav} onClose={() => setMobileNav(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenu={() => setMobileNav(true)} onSearch={() => setPalette(true)} />
        <main id="main" className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 md:px-6 lg:px-8">
          {children}
        </main>
      </div>
      <CommandPalette open={palette} onClose={closePalette} />
    </div>
  );
}
