import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="Portfolio"
      part={5}
      description="Paper-trading portfolios with transparent accounting. No brokerage connection."
      features={[
        "Simulated buys and sells with fees, cash balance and cost basis",
        "Realized vs. unrealized P&L, allocation, benchmark comparison",
        "Transactional consistency and tests for partial sales and missing prices",
      ]}
    />
  );
}
