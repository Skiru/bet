"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Zap, LayoutDashboard, FileText, Terminal } from "lucide-react";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/coupons", label: "Target Coupons", icon: FileText },
  { href: "/terminal", label: "Pipeline Terminal", icon: Terminal },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 shrink-0 bg-bg-sidebar border-r border-border-card flex flex-col">
      <div className="flex items-center gap-2.5 px-5 py-6">
        <Zap className="h-6 w-6 text-accent" />
        <span className="text-lg font-bold text-text-primary tracking-tight">
          BetOrchestrator
        </span>
      </div>
      <nav className="flex flex-col gap-1 px-3 mt-2">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-accent/15 text-accent"
                  : "text-text-secondary hover:bg-bg-card hover:text-text-primary"
              }`}
            >
              <item.icon className="h-4.5 w-4.5" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
