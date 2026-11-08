"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const NOTIFICATIONS_KEY = ["notifications"] as const;

/** Polls the server every minute; alert evaluation itself happens server-side after each ingestion. */
export function useNotifications() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: NOTIFICATIONS_KEY, queryFn: api.notifications, refetchInterval: 60_000, staleTime: 15_000 });
  const markRead = useMutation({
    mutationFn: (ids: number[] | null) => api.markNotificationsRead(ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
  return { ...q, markRead };
}
