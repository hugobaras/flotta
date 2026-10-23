"use client";

import { useEffect, useState } from "react";

export default function Parametres() {
  const [p, setP] = useState<{ heure_rappel: string; retention_jours: number; alert_emails: string[]; logo: boolean } | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetch("/api/admin/parametres").then(async (r) => {
      if (r.status === 401) return (window.location.href = "/connexion");
      setP(await r.json());
    });
  }, []);

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch("/api/admin/parametres", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ heure_rappel: p!.heure_rappel, retention_jours: p!.retention_jours, alert_emails: p!.alert_emails }),
    });
    setMessage(r.ok ? "Enregistré." : r.status === 403 ? "Réservé aux administrateurs." : "Valeurs invalides.");
  }

  async function envoyerLogo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const form = new FormData();
    form.append("logo", f);
    const r = await fetch("/api/admin/logo", { method: "POST", body: form });
    setMessage(r.ok ? "Logo enregistré." : r.status === 403 ? "Réservé aux administrateurs." : "Logo refusé (JPEG ou PNG, 1 Mo maximum).");
    if (r.ok) setP({ ...p!, logo: true });
  }

  if (!p) return <p>Chargement…</p>;

  return (
    <main>
      <h1>Paramètres</h1>
      <form onSubmit={enregistrer} style={{ display: "grid", gap: 8, maxWidth: 360 }}>
        <label>Heure du rappel (camions sans contrôle)
          <input type="time" value={p.heure_rappel} onChange={(e) => setP({ ...p, heure_rappel: e.target.value })} required />
        </label>
        <label>Conservation des contrôles, photos et positions (jours)
          <input type="number" min={30} max={3650} value={p.retention_jours} onChange={(e) => setP({ ...p, retention_jours: Number(e.target.value) })} required />
        </label>
        <label>Destinataires des alertes (un email par ligne)
          <textarea rows={3} value={p.alert_emails.join("\n")} onChange={(e) => setP({ ...p, alert_emails: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />
        </label>
        <button type="submit">Enregistrer</button>
      </form>
      <h2>Logo (PDF)</h2>
      {p.logo && <p><img src="/api/admin/logo" alt="Logo" height={40} /></p>}
      <input type="file" accept="image/png,image/jpeg" onChange={envoyerLogo} />
      {message && <p>{message}</p>}
    </main>
  );
}
