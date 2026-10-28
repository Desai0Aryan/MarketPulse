import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="Watchlists"
      part={3}
      description="Multiple persistent watchlists with performance at a glance."
      features={[
        "Create, rename, delete and reorder watchlists stored in PostgreSQL",
        "Default watchlist, symbol search, one-click alerts from any row",
        "Recent performance and sparklines per symbol",
      ]}
    />
  );
}
