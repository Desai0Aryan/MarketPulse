import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="Backtesting"
      part={6}
      description="Research simple strategies on historical data. Not trade execution."
      features={[
        "Moving-average crossover, RSI threshold and momentum strategies",
        "Next-bar execution, costs and slippage, tests that catch look-ahead bias",
        "Equity curve vs. buy-and-hold, drawdown, trade log, reproducible runs",
      ]}
    />
  );
}
