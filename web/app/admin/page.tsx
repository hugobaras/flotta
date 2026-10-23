"use client";

import { useEffect, useState } from "react";

type Vehicule = { id: number; plaque: string; token: string; bloque: boolean };

export default function Admin() {
  const [vehicules, setVehicules] = useState<Vehicule[] | null>(null);

  async function charger() {
    const r = await fetch("/api/admin/vehicules");
    if (r.status === 401) return (window.location.href = "/connexion");
    setVehicules(await r.json());
  }

  useEffect(() => {
    charger();
  }, []);

  async function debloquer(id: number) {
    await fetch(`/api/admin/vehicules/${id}/debloquer`, { method: "POST" });
    charger();
  }

  async function deconnexion() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/connexion";
  }

  if (!vehicules) return <p>Chargement…</p>;

  return (
    <main>
      <h1>Véhicules</h1>
      <button onClick={deconnexion}>Se déconnecter</button>
      <ul>
        {vehicules.map((v) => (
          <li key={v.id}>
            {v.plaque} : {v.bloque ? "bloqué" : "disponible"}{" "}
            {v.bloque && <button onClick={() => debloquer(v.id)}>Débloquer</button>}
          </li>
        ))}
      </ul>
    </main>
  );
}
