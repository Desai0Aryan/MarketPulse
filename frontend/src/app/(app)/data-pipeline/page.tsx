import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="Data Pipeline"
      part={2}
      description="Operational control center for ingestion, quality and freshness."
      features={[
        "Ingestion run history, success rate, retries, latency and rejected records",
        "Per-symbol checkpoints and data freshness",
        "Guarded manual ingest and historical backfill actions",
      ]}
    />
  );
}
