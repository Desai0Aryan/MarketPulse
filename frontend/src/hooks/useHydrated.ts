"use client";

import { useEffect, useState } from "react";

/** True after the first client render; use to avoid SSR/localStorage hydration mismatches. */
export function useHydrated() {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  return hydrated;
}
