"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NOTIFICATIONS_KEY } from "@/hooks/useNotifications";

export type LiveState = "connecting" | "live" | "polling";

/**
 * Subscribes to the server's SSE stream (/api/v1/events) and refreshes the affected queries when an ingestion run
 * finishes or an alert fires. EventSource reconnects by itself; if the stream can't be established (proxy buffering,
 * unsupported browser, server down) the state is "polling" and the pages' own refetch intervals keep data fresh.
 */
export function useLiveEvents(): LiveState {
  const qc = useQueryClient();
  const [state, setState] = useState<LiveState>("connecting");

  useEffect(() => {
    if (typeof EventSource === "undefined") { setState("polling"); return; }
    const es = new EventSource("/api/v1/events");
    let failures = 0;
    const refreshData = () => {
      for (const k of ["overview", "stocks", "prices", "watchlists", "pipeline", "portfolio", "pf-perf", "screen"]) qc.invalidateQueries({ queryKey: [k] });
    };
    const refreshAlerts = () => {
      for (const k of [NOTIFICATIONS_KEY[0], "alerts", "alert-events"]) qc.invalidateQueries({ queryKey: [k] });
    };
    es.addEventListener("hello", () => { failures = 0; setState("live"); });
    es.addEventListener("ingestion", () => { refreshData(); refreshAlerts(); });
    es.addEventListener("alert", refreshAlerts);
    es.onerror = () => {
      failures += 1;
      setState(failures >= 3 ? "polling" : "connecting"); // EventSource keeps retrying in the background
    };
    return () => es.close();
  }, [qc]);

  return state;
}
