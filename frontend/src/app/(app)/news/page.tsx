import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="News"
      part={6}
      description="Market headlines with source attribution and a labeled sentiment baseline."
      features={[
        "Real articles when a news provider key is configured; clearly labeled sample content otherwise",
        "Deduplication, filters by symbol, source and date",
        "Deterministic local sentiment baseline with documented limitations",
      ]}
    />
  );
}
