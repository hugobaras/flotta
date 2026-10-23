"use client";

import { useEffect, useState } from "react";

type Controle = { id: number; plaque: string; conducteur: string; defaut_critique: boolean; has_defaut: boolean; created_at: string };

export default function Controles() {
  const [filtres, setFiltres] = useState({ date: "", conducteur: "", defaut: false });
  const [lignes, setLignes] = useState<Controle[] | null>(null);

  useEffect(() => {
    const p = new URLSearchParams();
    if (filtres.date) p.set("date", filtres.date);
    if (filtres.conducteur) p.set("conducteur", filtres.conducteur);
    if (filtres.defaut) p.set("defaut", "true");
    fetch(`/api/admin/controles?${p}`).then(async (r) => {
      if (r.status === 401) return (window.location.href = "/connexion");
      setLignes(await r.json());
    });
  }, [filtres]);

  return (
    <main>
      <h1>Contrôles</h1>
      <input type="date" value={filtres.date} onChange={(e) => setFiltres({ ...filtres, date: e.target.value })} />{" "}
      <input placeholder="Conducteur" value={filtres.conducteur} onChange={(e) => setFiltres({ ...filtres, conducteur: e.target.value })} />{" "}
      <label>
        <input type="checkbox" checked={filtres.defaut} onChange={(e) => setFiltres({ ...filtres, defaut: e.target.checked })} /> défauts seulement
      </label>
      {!lignes ? <p>Chargement…</p> : lignes.length === 0 ? <p>Aucun contrôle.</p> : (
        <ul>
          {lignes.map((c) => (
            <li key={c.id}>
              <a href={`/admin/controles/${c.id}`}>
                {new Date(c.created_at).toLocaleString("fr-FR")} · {c.plaque} · {c.conducteur}
              </a>
              {c.defaut_critique ? " · défaut critique" : c.has_defaut ? " · défaut" : ""}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
