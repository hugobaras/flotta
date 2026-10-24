"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Brand } from "../ui";

const NAV = [
  { href: "/admin", label: "Aujourd'hui", exact: true, aussi: "/admin/controles" },
  { href: "/admin/planning", label: "Planning" },
  { href: "/admin/configuration", label: "Configuration" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [email, setEmail] = useState("");
  const [plateforme, setPlateforme] = useState(false);

  useEffect(() => {
    fetch("/api/auth/me").then(async (r) => {
      if (r.status === 401) return (window.location.href = "/connexion");
      const me = await r.json();
      setEmail(me.email);
      setPlateforme(me.role === "plateforme");
    });
  }, []);

  const dialogue = useRef<HTMLDialogElement>(null);
  const [message, setMessage] = useState("");
  const [envoi, setEnvoi] = useState<"" | "ok" | "ko">("");

  async function signaler(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch("/api/admin/signalements", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, page: window.location.pathname, navigateur: navigator.userAgent }) });
    setEnvoi(r.ok ? "ok" : "ko");
    if (r.ok) setMessage("");
  }

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
            {[...NAV, ...(plateforme ? [{ href: "/admin/plateforme", label: "Plateforme" }] : [])].map(({ href, label, exact, aussi }) => (
              <Link key={href} href={href} aria-current={((exact ? path === href : path.startsWith(href)) || (aussi && path.startsWith(aussi))) ? "page" : undefined}>{label}</Link>
            ))}
          </nav>
          <div className="who">
            <span className="email" title={email}>{email}</span>
            <button className="btn btn-ghost btn-sm" onClick={deconnexion}>Déconnexion</button>
          </div>
        </div>
      </header>
      <main className="wrap">{children}</main>
      <footer className="pied-app">
        <button className="link-btn" onClick={() => { setEnvoi(""); dialogue.current?.showModal(); }}>Signaler un problème</button>
      </footer>
      <dialog ref={dialogue} className="dialog" aria-labelledby="signal-titre">
        <form onSubmit={signaler} style={{ display: "grid", gap: 14, padding: 24 }}>
          <div>
            <h2 id="signal-titre">Signaler un problème</h2>
            <p className="muted" style={{ marginTop: 6 }}>Décrivez ce qui ne va pas. La page, votre société et la version sont jointes automatiquement.</p>
          </div>
          {envoi === "ok" ? <div className="notice" role="status" style={{ margin: 0 }}>Merci, votre message est transmis.</div> : (
            <textarea className="input" required minLength={3} maxLength={2000} rows={5} aria-label="Votre message" value={message} onChange={(e) => setMessage(e.target.value)} />
          )}
          {envoi === "ko" && <div className="notice danger" role="alert" style={{ margin: 0 }}>Envoi impossible, réessayez.</div>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => dialogue.current?.close()}>Fermer</button>
            {envoi !== "ok" && <button className="btn btn-primary">Envoyer</button>}
          </div>
        </form>
      </dialog>
    </>
  );
}
