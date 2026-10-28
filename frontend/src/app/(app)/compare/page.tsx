import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="Compare"
      part={4}
      description="Side-by-side performance and risk for two to ten stocks."
      features={[
        "Normalized performance chart rebased to 100",
        "Volatility, max drawdown, correlation matrix and rolling correlation",
        "Documented handling of missing sessions and CSV export",
      ]}
    />
  );
}
