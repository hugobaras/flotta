"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "../ui";

const NAV = [
  { href: "/admin", label: "Tableau de bord", exact: true },
  { href: "/admin/controles", label: "Contrôles" },
  { href: "/admin/checklists", label: "Checklists" },
  { href: "/admin/parametres", label: "Paramètres" },
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
    <>
      <header className="band">
        <div className="band-in">
          <Brand href="/admin" />
          <nav className="nav" aria-label="Navigation principale">
            {NAV.map(({ href, label, exact }) => (
              <Link key={href} href={href} aria-current={(exact ? path === href : path.startsWith(href)) ? "page" : undefined}>{label}</Link>
            ))}
          </nav>
          <div className="who">
            <span className="email" title={email}>{email}</span>
            <button className="btn btn-ghost btn-sm" onClick={deconnexion}>Déconnexion</button>
          </div>
        </div>
      </header>
      <main className="wrap">{children}</main>
    </>
  );
}
