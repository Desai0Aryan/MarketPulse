import {
  Activity, Bell, BarChart3, Bot, Briefcase, FlaskConical, GitCompare, LayoutDashboard,
  ListFilter, Newspaper, Settings, Star, Workflow, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Roadmap part in which the page becomes fully functional. */
  part: number;
  group: "Overview" | "Analysis" | "Tools" | "System";
}

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, part: 1, group: "Overview" },
  { href: "/markets", label: "Markets", icon: BarChart3, part: 1, group: "Overview" },
  { href: "/watchlists", label: "Watchlists", icon: Star, part: 3, group: "Overview" },
  { href: "/screener", label: "Screener", icon: ListFilter, part: 4, group: "Analysis" },
  { href: "/compare", label: "Compare", icon: GitCompare, part: 4, group: "Analysis" },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase, part: 5, group: "Analysis" },
  { href: "/backtesting", label: "Backtesting", icon: FlaskConical, part: 6, group: "Tools" },
  { href: "/alerts", label: "Alerts", icon: Bell, part: 5, group: "Tools" },
  { href: "/news", label: "News", icon: Newspaper, part: 6, group: "Tools" },
  { href: "/ai-research", label: "AI Research", icon: Bot, part: 6, group: "Tools" },
  { href: "/data-pipeline", label: "Data Pipeline", icon: Workflow, part: 2, group: "System" },
  { href: "/settings", label: "Settings", icon: Settings, part: 1, group: "System" },
];

export const BRAND_ICON = Activity;
