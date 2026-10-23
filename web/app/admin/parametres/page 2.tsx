"use client";

import { useEffect, useState } from "react";

export default function Parametres() {
  const [p, setP] = useState<{ heure_rappel: string; retention_jours: number } | null>(null);
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
      body: JSON.stringify(p),
    });
    setMessage(r.ok ? "Enregistré." : r.status === 403 ? "Réservé aux administrateurs." : "Valeurs invalides.");
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
        <button type="submit">Enregistrer</button>
      </form>
      {message && <p>{message}</p>}
    </main>
  );
}
