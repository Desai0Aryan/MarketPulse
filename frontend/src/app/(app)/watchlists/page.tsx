"use client";

import { useMutation } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Pencil, Plus, Search, Star, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Sparkline } from "@/components/charts/Sparkline";
import { Change } from "@/components/shared/Change";
import { Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useCacheUpdater, useWatchlists, WATCHLISTS_KEY } from "@/hooks/useWatchlists";
import { api } from "@/lib/api";
import { cn, usd } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import type { Watchlist } from "@/types/api";

function useDebounced<T>(value: T, ms = 200) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

function AddSymbol({ wl, onChange }: { wl: Watchlist; onChange: (w: Watchlist) => void }) {
  const [term, setTerm] = useState("");
  const debounced = useDebounced(term.trim());
  const [err, setErr] = useState<string | null>(null);
  const res = useQuery({ queryKey: ["search", debounced], queryFn: () => api.search(debounced), enabled: debounced.length > 0, staleTime: 60_000 });

  const add = async (symbol: string) => {
    setErr(null);
    try {
      onChange(await api.addWatchlistItem(wl.id, symbol));
      setTerm("");
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="border-b border-border p-3">
      <label className="flex items-center gap-2 rounded-lg border border-border bg-bg/60 px-3 focus-within:border-accent">
        <Search className="h-4 w-4 text-muted" aria-hidden />
        <span className="sr-only">Add a symbol</span>
        <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Add a symbol or company…" className="h-9 flex-1 bg-transparent text-sm outline-none placeholder:text-muted" />
      </label>
      {debounced && (
        <ul className="mt-2 space-y-0.5" aria-label="Search results">
          {res.isLoading && <li className="px-2 py-1.5 text-xs text-muted">Searching…</li>}
          {res.isError && <li className="px-2 py-1.5 text-xs text-down">{(res.error as Error).message}</li>}
          {res.data?.items.length === 0 && <li className="px-2 py-1.5 text-xs text-muted">No symbols match “{debounced}”.</li>}
          {res.data?.items.map((r) => {
            const has = wl.symbols.includes(r.symbol);
            return (
              <li key={r.symbol}>
                <button onClick={() => add(r.symbol)} disabled={has} className="flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-elevated disabled:opacity-50">
                  <span className="w-14 font-semibold">{r.symbol}</span>
                  <span className="flex-1 truncate text-muted">{r.name}</span>
                  {has ? <Badge>Added</Badge> : <Plus className="h-4 w-4 text-accent" aria-label={`Add ${r.symbol}`} />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {err && <p role="alert" className="mt-2 text-xs text-down">{err}</p>}
    </div>
  );
}

export default function WatchlistsPage() {
  const qc = useQueryClient();
  const q = useWatchlists();
  const update = useCacheUpdater();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const lists = q.data?.items ?? [];
  const sel = lists.find((w) => w.id === selectedId) ?? lists.find((w) => w.is_default) ?? lists[0];
  const fail = (e: unknown) => setMsg({ ok: false, text: (e as Error).message });

  const create = useMutation({
    mutationFn: () => api.createWatchlist(newName),
    onSuccess: (wl) => {
      qc.invalidateQueries({ queryKey: WATCHLISTS_KEY });
      setSelectedId(wl.id);
      setNewName("");
      setMsg({ ok: true, text: `Created “${wl.name}”.` });
    },
    onError: fail,
  });
  const patch = useMutation({
    mutationFn: (b: { id: number; name?: string; is_default?: boolean }) => api.updateWatchlist(b.id, { name: b.name, is_default: b.is_default }),
    onSuccess: (wl) => { update(wl); setRenaming(null); setMsg(null); },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteWatchlist(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: WATCHLISTS_KEY }); setSelectedId(null); setMsg({ ok: true, text: "Watchlist deleted." }); },
    onError: fail,
  });
  const reorder = useMutation({
    mutationFn: (b: { id: number; symbols: string[] }) => api.reorderWatchlist(b.id, b.symbols),
    onSuccess: update,
    onError: fail,
  });
  const removeItem = useMutation({
    mutationFn: (b: { id: number; symbol: string }) => api.removeWatchlistItem(b.id, b.symbol),
    onSuccess: update,
    onError: fail,
  });

  const move = (wl: Watchlist, i: number, dir: -1 | 1) => {
    const next = [...wl.symbols];
    const j = i + dir;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j]!, next[i]!];
    reorder.mutate({ id: wl.id, symbols: next });
  };

  return (
    <>
      <PageHeader title="Watchlists" description="Your lists are stored by the server and shared across the dashboard, markets and stock pages." />
      {q.isError ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
      ) : q.isLoading ? (
        <div className="grid gap-5 lg:grid-cols-[280px_1fr]"><Skeleton className="h-64" /><Skeleton className="h-96" /></div>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[280px_1fr]">
          <Card>
            <CardHeader title="Your lists" subtitle={`${lists.length} of 20`} />
            <ul className="px-2 pb-2">
              {lists.map((w) => (
                <li key={w.id}>
                  <button onClick={() => setSelectedId(w.id)} aria-current={sel?.id === w.id} className={cn("flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm", sel?.id === w.id ? "bg-accent/12 text-fg" : "text-muted hover:bg-elevated hover:text-fg")}>
                    <span className="flex-1 truncate font-medium">{w.name}</span>
                    {w.is_default && <Badge tone="accent">Default</Badge>}
                    <span className="num text-[11px]">{w.symbols.length}</span>
                  </button>
                </li>
              ))}
            </ul>
            <form className="flex gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) create.mutate(); }}>
              <label className="sr-only" htmlFor="new-list">New watchlist name</label>
              <input id="new-list" value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={40} placeholder="New list name" className="min-w-0 flex-1 rounded-lg border border-border bg-bg/60 px-2.5 py-1.5 text-sm outline-none focus:border-accent" />
              <button type="submit" disabled={!newName.trim() || create.isPending} aria-label="Create watchlist" className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white disabled:opacity-50"><Plus className="h-4 w-4" /></button>
            </form>
            {msg && <p role="status" className={cn("px-3 pb-3 text-xs", msg.ok ? "text-up" : "text-down")}>{msg.text}</p>}
          </Card>

          {sel ? (
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4">
                {renaming !== null ? (
                  <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); patch.mutate({ id: sel.id, name: renaming }); }}>
                    <label className="sr-only" htmlFor="rename">Rename watchlist</label>
                    <input id="rename" autoFocus value={renaming} onChange={(e) => setRenaming(e.target.value)} maxLength={40} className="rounded-lg border border-border bg-bg/60 px-2.5 py-1.5 text-sm outline-none focus:border-accent" />
                    <button type="submit" className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white">Save</button>
                    <button type="button" onClick={() => setRenaming(null)} aria-label="Cancel rename" className="rounded-md p-1.5 text-muted hover:bg-elevated"><X className="h-4 w-4" /></button>
                  </form>
                ) : (
                  <h2 className="text-lg font-semibold">{sel.name}</h2>
                )}
                <div className="flex items-center gap-1.5">
                  <button onClick={() => patch.mutate({ id: sel.id, is_default: true })} disabled={sel.is_default} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium hover:border-accent/60 disabled:opacity-50"><Star className={cn("h-3.5 w-3.5", sel.is_default && "fill-warn text-warn")} aria-hidden /> {sel.is_default ? "Default" : "Make default"}</button>
                  <button onClick={() => setRenaming(sel.name)} aria-label="Rename watchlist" className="grid h-8 w-8 place-items-center rounded-lg border border-border text-muted hover:text-fg"><Pencil className="h-3.5 w-3.5" /></button>
                  <button
                    onClick={() => { if (window.confirm(`Delete “${sel.name}”? This cannot be undone.`)) remove.mutate(sel.id); }}
                    aria-label="Delete watchlist"
                    className="grid h-8 w-8 place-items-center rounded-lg border border-border text-down hover:bg-down/10"
                  ><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              </div>
              <div className="mt-3"><AddSymbol wl={sel} onChange={update} /></div>
              {sel.items.length === 0 ? (
                <EmptyState title="This list is empty" hint="Search above to add your first symbol." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] text-sm">
                    <thead className="border-b border-border text-[11px] uppercase tracking-wider text-muted">
                      <tr><th className="px-4 py-2 text-left font-medium">Symbol</th><th className="px-3 py-2 text-right font-medium">Price</th><th className="px-3 py-2 text-right font-medium">Change</th><th className="px-3 py-2 text-right font-medium">30D</th><th className="px-3 py-2 text-right font-medium">Order</th></tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {sel.items.map((it, i) => (
                        <tr key={it.symbol} className="hover:bg-elevated/60">
                          <td className="px-4 py-2.5">
                            <Link href={`/markets/${it.symbol}`} className="block font-semibold hover:text-accent">{it.symbol}</Link>
                            <div className="max-w-[240px] truncate text-[11px] text-muted">{it.name}</div>
                          </td>
                          {it.has_data ? (
                            <>
                              <td className="num px-3 py-2.5 text-right font-medium">{usd(it.price!)}</td>
                              <td className="px-3 py-2.5 text-right"><Change change={it.change!} changePct={it.change_pct!} showAbs={false} /></td>
                              <td className="px-3 py-2.5"><div className="flex justify-end"><Sparkline data={it.sparkline!} width={72} height={24} fill={false} /></div></td>
                            </>
                          ) : (
                            <td colSpan={3} className="px-3 py-2.5 text-right text-xs text-muted">No stored data yet</td>
                          )}
                          <td className="px-3 py-2.5">
                            <div className="flex justify-end gap-1">
                              <button onClick={() => move(sel, i, -1)} disabled={i === 0 || reorder.isPending} aria-label={`Move ${it.symbol} up`} className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-elevated disabled:opacity-30"><ArrowUp className="h-3.5 w-3.5" /></button>
                              <button onClick={() => move(sel, i, 1)} disabled={i === sel.items.length - 1 || reorder.isPending} aria-label={`Move ${it.symbol} down`} className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-elevated disabled:opacity-30"><ArrowDown className="h-3.5 w-3.5" /></button>
                              <button onClick={() => removeItem.mutate({ id: sel.id, symbol: it.symbol })} aria-label={`Remove ${it.symbol}`} className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-down/10 hover:text-down"><X className="h-3.5 w-3.5" /></button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          ) : (
            <Card><EmptyState title="No watchlists yet" hint="Create one on the left." /></Card>
          )}
        </div>
      )}
    </>
  );
}
