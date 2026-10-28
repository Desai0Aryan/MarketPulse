import { PlannedPage } from "@/components/shared/PlannedPage";

export default function Page() {
  return (
    <PlannedPage
      title="AI Research"
      part={6}
      description="A research copilot grounded in your platform's own data."
      features={[
        "Answers built from validated backend tools, never raw SQL",
        "Citations and data timestamps; says so when data is unavailable",
        "Fully optional: the platform works without any LLM key",
      ]}
    />
  );
}
