"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Watchlist } from "@/types/api";

export const WATCHLISTS_KEY = ["watchlists"] as const;

export function useWatchlists() {
  return useQuery({ queryKey: WATCHLISTS_KEY, queryFn: api.watchlists, staleTime: 15_000 });
}

/** Replace one list in the cached collection with the server's response (keeps every view in sync). */
export function useCacheUpdater() {
  const qc = useQueryClient();
  return (wl: Watchlist) =>
    qc.setQueryData<{ items: Watchlist[] }>(WATCHLISTS_KEY, (old) => {
      if (!old) return old;
      const others = old.items.map((w) => (wl.is_default && w.id !== wl.id ? { ...w, is_default: false } : w));
      return { items: others.map((w) => (w.id === wl.id ? wl : w)) };
    });
}

export function useDefaultWatchlist() {
  const q = useWatchlists();
  const update = useCacheUpdater();
  const def = q.data?.items.find((w) => w.is_default) ?? q.data?.items[0];
  const toggle = useMutation({
    mutationFn: ({ symbol, remove }: { symbol: string; remove: boolean }) => {
      if (!def) throw new Error("No watchlist available");
      return remove ? api.removeWatchlistItem(def.id, symbol) : api.addWatchlistItem(def.id, symbol);
    },
    onSuccess: update,
  });
  return { watchlist: def, has: (s: string) => !!def?.symbols.includes(s), toggle, isLoading: q.isLoading };
}
