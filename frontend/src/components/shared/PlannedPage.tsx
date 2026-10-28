import { Check, Circle } from "lucide-react";
import { Badge, Card, CardHeader, PageHeader } from "@/components/ui/primitives";
import { ROADMAP } from "@/lib/roadmap";

/** Honest status page for features scheduled in a later build part. */
export function PlannedPage({ title, part, description, features }: { title: string; part: number; description: string; features: string[] }) {
  const info = ROADMAP.find((r) => r.id === part);
  return (
    <>
      <PageHeader title={title} description={description} actions={<Badge tone="accent">Ships in Part {part}</Badge>} />
      <Card className="max-w-3xl">
        <CardHeader title="Planned for this page" subtitle={info ? `Part ${part} — ${info.title}` : undefined} />
        <ul className="space-y-2.5 px-4 pb-5 pt-2">
          {features.map((f) => (
            <li key={f} className="flex items-start gap-3 text-sm">
              <Circle className="mt-1 h-3 w-3 shrink-0 text-muted" aria-hidden />
              <span>{f}</span>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2 border-t border-border px-4 py-3 text-xs text-muted">
          <Check className="h-3.5 w-3.5 text-up" aria-hidden />
          Nothing on this page is mocked: it will be built against real backend endpoints.
        </div>
      </Card>
    </>
  );
}
