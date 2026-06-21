"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ThemeToggle } from "./ThemeToggle";

const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:7000";
const NAV = [
  { href: "/", label: "New Research", icon: "compass" },
  { href: "/history", label: "History", icon: "clock" },
  { href: "/settings", label: "API Keys", icon: "key" },
];

function Trident() {
  // ATHENA's mark (🔱) — white trident on the brand-mark's orange square
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M5.5 8.5H18.5" /><path d="M4.4 3.4 5.5 8.5" /><path d="M12 8.5V2.6" />
      <path d="M19.6 3.4 18.5 8.5" /><path d="M12 8.5V19.6" /><path d="M9.2 19.6h5.6" />
    </svg>
  );
}

function Icon({ name }: { name: string }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (name === "compass") return (<svg {...common}><circle cx="12" cy="12" r="9" /><polygon points="16.2 7.8 13.4 13.4 7.8 16.2 10.6 10.6 16.2 7.8" /></svg>);
  if (name === "clock") return (<svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>);
  return (<svg {...common}><circle cx="8" cy="8" r="3.2" /><path d="M10.5 10.5 20 20M16 16l2-2M19 13l2 2" /></svg>);
}

export function Sidebar() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    const ping = () => fetch(`${BASE}/api/health`)
      .then((r) => { if (alive) setOnline(r.ok); })
      .catch(() => { if (alive) setOnline(false); });
    ping();
    const id = setInterval(ping, 15000);   // keep the status dot fresh, not a one-shot at load
    return () => { alive = false; clearInterval(id); };
  }, []);
  return (
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Trident /></span><span className="brand-name">ATHENA</span></div>
      <nav className="nav">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className={`nav-item ${path === n.href ? "active" : ""}`}>
            <Icon name={n.icon} /><span>{n.label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-foot">
        <ThemeToggle />
        <div className="api-status">
          <span className={`dot ${online ? "ok" : online === false ? "bad" : ""}`} />
          {online == null ? "checking…" : online ? "api online" : "api offline"}
        </div>
      </div>
    </aside>
  );
}
