"use client";

import { useEffect, useState } from "react";

type Item = { id: number; libelle: string; critique: boolean; actif: boolean };
type Modele = { id: number; nom: string; vehicle_type: string; items: Item[] };

const json = { "Content-Type": "application/json" };

export default function Checklists() {
  const [modeles, setModeles] = useState<Modele[] | null>(null);
  const [nouveau, setNouveau] = useState("");

  async function charger() {
    const r = await fetch("/api/admin/checklists");
    if (r.status === 401) return (window.location.href = "/connexion");
    setModeles(await r.json());
  }

  useEffect(() => {
    charger();
  }, []);

  async function appeler(url: string, method: string, body: object) {
    await fetch(url, { method, headers: json, body: JSON.stringify(body) });
    charger();
  }

  const modifier = (i: Item, champs: Partial<Item>) => appeler(`/api/admin/checklists/items/${i.id}`, "PATCH", champs);
  const deplacer = (i: Item, sens: "haut" | "bas") => appeler(`/api/admin/checklists/items/${i.id}/deplacer`, "POST", { sens });

  async function renommer(i: Item) {
    const libelle = window.prompt("Libellé du point", i.libelle);
    if (libelle?.trim()) modifier(i, { libelle });
  }

  if (!modeles) return <p>Chargement…</p>;

  return (
    <main>
      <h1>Checklists</h1>
      {modeles.map((m) => (
        <section key={m.id}>
          <h2>{m.nom} <small>({m.vehicle_type})</small></h2>
          <ol>
            {m.items.map((i, n) => (
              <li key={i.id} style={{ opacity: i.actif ? 1 : 0.5, marginBottom: 6 }}>
                {i.libelle}{" "}
                <button onClick={() => deplacer(i, "haut")} disabled={n === 0} aria-label="Monter">↑</button>
                <button onClick={() => deplacer(i, "bas")} disabled={n === m.items.length - 1} aria-label="Descendre">↓</button>
                <button onClick={() => renommer(i)}>Renommer</button>
                <label>
                  <input type="checkbox" checked={i.critique} onChange={(e) => modifier(i, { critique: e.target.checked })} /> critique
                </label>
                <label>
                  <input type="checkbox" checked={i.actif} onChange={(e) => modifier(i, { actif: e.target.checked })} /> actif
                </label>
              </li>
            ))}
          </ol>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              appeler(`/api/admin/checklists/${m.id}/items`, "POST", { libelle: nouveau }).then(() => setNouveau(""));
            }}
          >
            <input placeholder="Nouveau point" value={nouveau} onChange={(e) => setNouveau(e.target.value)} required />
            <button type="submit">Ajouter</button>
          </form>
        </section>
      ))}
    </main>
  );
}
