"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import { AuthGate } from "./AuthGate";
import { LensMark } from "./LensMark";

const NAV = [
  { href: "/chat", label: "Ask", num: "01" },
  { href: "/search", label: "Search", num: "02" },
  { href: "/admin", label: "Admin", num: "03" },
];

function Rail() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <nav className="rail" aria-label="Primary">
      <Link className="brand" href="/chat">
        <LensMark size={26} />
        <span className="brand-name">
          Now<b>Lens</b>
        </span>
      </Link>

      <div className="nav">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="nav-link"
            data-active={pathname === item.href || pathname?.startsWith(item.href + "/")}
          >
            <span className="num">{item.num}</span>
            {item.label}
          </Link>
        ))}
      </div>

      <div className="rail-foot">
        {user && (
          <>
            <span className="who">{user.email}</span>
            <span className="role">{user.role}</span>
            <div style={{ marginTop: 12 }}>
              <button className="btn-ghost" style={{ padding: "6px 0" }} onClick={logout}>
                Sign out
              </button>
            </div>
          </>
        )}
      </div>
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <div className="shell">
        <Rail />
        <main className="main">{children}</main>
      </div>
    </AuthGate>
  );
}
