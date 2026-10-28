import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { cn, pct, signed, trendClass } from "@/lib/utils";

/** Price change. Uses an icon + sign in addition to color so status isn't conveyed by color alone. */
export function Change({ change, changePct, className, showAbs = true }: { change: number; changePct: number; className?: string; showAbs?: boolean }) {
  const Icon = changePct > 0 ? ArrowUpRight : changePct < 0 ? ArrowDownRight : Minus;
  return (
    <span className={cn("num inline-flex items-center gap-1 text-sm font-medium", trendClass(changePct), className)}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {showAbs && <span>{signed(change)}</span>}
      <span className={showAbs ? "opacity-80" : ""}>{showAbs ? `(${pct(changePct)})` : pct(changePct)}</span>
    </span>
  );
}
