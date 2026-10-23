"use client";

import { useEffect, useState } from "react";

type Ligne = { vehicle_id: number; plaque: string; statut: string; controle: { id: number; conducteur: string; created_at: string } | null };
type Rappels = { heure_rappel: string; vehicules: { id: number; plaque: string }[] };

const LIBELLES: Record<string, string> = { controle: "Contrôlé", non_controle: "Non contrôlé", defaut: "Défaut", bloque: "Bloqué" };

export default function Admin() {
  const [date, setDate] = useState("");
  const [lignes, setLignes] = useState<Ligne[] | null>(null);
  const [rappels, setRappels] = useState<Rappels | null>(null);

  async function charger() {
    const r = await fetch(`/api/admin/tableau${date ? `?date=${date}` : ""}`);
    if (r.status === 401) return (window.location.href = "/connexion");
    setLignes((await r.json()).vehicules);
    setRappels(await (await fetch("/api/admin/rappels")).json());
  }

  useEffect(() => {
    charger();
  }, [date]);

  async function debloquer(l: Ligne) {
    const commentaire = window.prompt(`Pourquoi débloquer ${l.plaque} ? (obligatoire)`);
    if (!commentaire?.trim()) return;
    const r = await fetch(`/api/admin/vehicules/${l.vehicle_id}/debloquer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commentaire }),
    });
    if (!r.ok) window.alert("Déblocage impossible.");
    charger();
  }

  async function deconnexion() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/connexion";
  }

  if (!lignes) return <p>Chargement…</p>;

  return (
    <main>
      <h1>Tableau de bord</h1>
      <label>
        Jour : <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>{" "}
      <button onClick={deconnexion}>Se déconnecter</button>
      {rappels && rappels.vehicules.length > 0 && (
        <p role="alert">
          Sans contrôle depuis {rappels.heure_rappel} : {rappels.vehicules.map((v) => v.plaque).join(", ")}
        </p>
      )}
      <table>
        <tbody>
          {lignes.map((l) => (
            <tr key={l.vehicle_id}>
              <td>{l.plaque}</td>
              <td>{LIBELLES[l.statut]}</td>
              <td>{l.controle && <a href={`/admin/controles/${l.controle.id}`}>{l.controle.conducteur}</a>}</td>
              <td>{l.statut === "bloque" && <button onClick={() => debloquer(l)}>Débloquer</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
