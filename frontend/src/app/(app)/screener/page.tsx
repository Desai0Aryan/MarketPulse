import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="Screener"
      part={4}
      description="Filter the tracked universe by price, momentum, volatility and technicals."
      features={[
        "Server-side filtering on price, volume, RSI, volatility and distance from 52-week high",
        "Saved screens, CSV export, add results to a watchlist or comparison",
        "Filters that need unavailable data are disabled with an explanation",
      ]}
    />
  );
}
