"use client";

import { ChevronDown, ChevronUp, Pencil, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type Item = { id: number; libelle: string; critique: boolean; actif: boolean };
type Modele = { id: number; nom: string; vehicle_type: string; items: Item[] };

const json = { "Content-Type": "application/json" };
const TYPES: Record<string, string> = { poids_lourd: "Poids lourd" };

export default function Checklists() {
  const [modeles, setModeles] = useState<Modele[] | null>(null);
  const [nouveau, setNouveau] = useState<Record<number, string>>({});
  const [edition, setEdition] = useState<{ id: number; libelle: string } | null>(null);

  const charger = useCallback(async () => {
    const r = await fetch("/api/admin/checklists");
    if (r.status === 401) return (window.location.href = "/connexion");
    setModeles(await r.json());
  }, []);

  useEffect(() => {
    charger();
  }, [charger]);

  async function appeler(url: string, method: string, body: object) {
    await fetch(url, { method, headers: json, body: JSON.stringify(body) });
    await charger();
  }

  const modifier = (i: Item, champs: Partial<Item>) => appeler(`/api/admin/checklists/items/${i.id}`, "PATCH", champs);
  const deplacer = (i: Item, sens: "haut" | "bas") => appeler(`/api/admin/checklists/items/${i.id}/deplacer`, "POST", { sens });

  if (!modeles) return <p className="muted">Chargement…</p>;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Checklists</h1>
          <p>Les points que le chauffeur contrôle avant de partir. Un point critique bloque le camion s'il est en défaut.</p>
        </div>
      </div>

      <div className="stack-lg">
        {modeles.map((m) => (
          <section key={m.id} className="panel" aria-labelledby={`m${m.id}`}>
            <div className="panel-head">
              <h2 id={`m${m.id}`}>{m.nom}</h2>
              <span className="badge badge-accent">{TYPES[m.vehicle_type] ?? m.vehicle_type}</span>
            </div>
            <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {m.items.map((i, n) => (
                <li key={i.id} className={`item-row ${i.actif ? "" : "is-off"}`}>
                  <div className="move">
                    <button className="btn btn-ghost btn-icon btn-sm" style={{ height: 22 }} onClick={() => deplacer(i, "haut")} disabled={n === 0} aria-label={`Monter « ${i.libelle} »`}><ChevronUp aria-hidden /></button>
                    <button className="btn btn-ghost btn-icon btn-sm" style={{ height: 22 }} onClick={() => deplacer(i, "bas")} disabled={n === m.items.length - 1} aria-label={`Descendre « ${i.libelle} »`}><ChevronDown aria-hidden /></button>
                  </div>
                  {edition?.id === i.id ? (
                    <form
                      style={{ display: "flex", gap: 8, flex: 1 }}
                      onSubmit={async (e) => {
                        e.preventDefault();
                        if (edition.libelle.trim()) await modifier(i, { libelle: edition.libelle });
                        setEdition(null);
                      }}
                    >
                      <input className="input" aria-label="Libellé du point" value={edition.libelle} maxLength={200} onChange={(e) => setEdition({ id: i.id, libelle: e.target.value })} autoFocus />
                      <button className="btn btn-primary btn-sm" type="submit">Enregistrer</button>
                      <button className="btn btn-sm" type="button" onClick={() => setEdition(null)}>Annuler</button>
                    </form>
                  ) : (
                    <>
                      <span className="item-label">{i.libelle}</span>
                      <div className="item-controls">
                        <button className="btn btn-ghost btn-icon" onClick={() => setEdition({ id: i.id, libelle: i.libelle })} aria-label={`Renommer « ${i.libelle} »`}><Pencil aria-hidden /></button>
                        <label className="switch"><input type="checkbox" role="switch" checked={i.critique} onChange={(e) => modifier(i, { critique: e.target.checked })} />Critique</label>
                        <label className="switch"><input type="checkbox" role="switch" checked={i.actif} onChange={(e) => modifier(i, { actif: e.target.checked })} />Actif</label>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ol>
            <form
              className="add-row"
              onSubmit={async (e) => {
                e.preventDefault();
                await appeler(`/api/admin/checklists/${m.id}/items`, "POST", { libelle: nouveau[m.id] });
                setNouveau({ ...nouveau, [m.id]: "" });
              }}
            >
              <input className="input" aria-label="Nouveau point" placeholder="Ajouter un point, par exemple « Extincteur »" value={nouveau[m.id] ?? ""} maxLength={200} onChange={(e) => setNouveau({ ...nouveau, [m.id]: e.target.value })} required />
              <button className="btn btn-primary" type="submit"><Plus aria-hidden />Ajouter</button>
            </form>
          </section>
        ))}
      </div>
    </>
  );
}
