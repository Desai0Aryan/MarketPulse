import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="Alerts"
      part={5}
      description="Price and indicator alerts evaluated against stored data."
      features={[
        "Price, percent-change, RSI, moving-average cross and volume conditions",
        "Edge-triggered with cooldowns so ingestion cycles don't spam you",
        "Evaluation history with the observed value and timestamp",
      ]}
    />
  );
}
