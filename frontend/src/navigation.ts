import type { RouteName } from "./router.js";

export interface NavigationItem {
  href: string;
  label: string;
  route: RouteName;
  icon: string;
}

export const primaryNavigation: readonly NavigationItem[] = [
  { href: "/", label: "Overview", route: "overview", icon: "⌂" },
  { href: "/articles", label: "Articles", route: "articles", icon: "▤" },
  { href: "/forms", label: "Forms", route: "forms", icon: "＋" },
];

export const generationHref = "/generate";
