"use client";

import { ClipboardCheck, LayoutDashboard, ListChecks, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "../ui";

const NAV = [
  { href: "/admin", label: "Tableau de bord", Icon: LayoutDashboard, exact: true },
  { href: "/admin/controles", label: "Contrôles", Icon: ClipboardCheck },
  { href: "/admin/checklists", label: "Checklists", Icon: ListChecks },
  { href: "/admin/parametres", label: "Paramètres", Icon: Settings },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [email, setEmail] = useState("");

  useEffect(() => {
    fetch("/api/auth/me").then(async (r) => {
      if (r.status === 401) return (window.location.href = "/connexion");
      setEmail((await r.json()).email);
    });
  }, []);

  async function deconnexion() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/connexion";
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Brand href="/admin" />
        <nav className="nav" aria-label="Navigation principale">
          {NAV.map(({ href, label, Icon, exact }) => (
            <Link key={href} href={href} aria-current={(exact ? path === href : path.startsWith(href)) ? "page" : undefined}>
              <Icon aria-hidden /><span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="who" title={email}>{email}</div>
          <button className="btn btn-sm" onClick={deconnexion}><LogOut aria-hidden />Se déconnecter</button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
