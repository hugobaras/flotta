"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { dateHeure, Etat, Plaque } from "../../ui";

type Controle = { id: number; plaque: string; conducteur: string; defaut_critique: boolean; has_defaut: boolean; created_at: string };

export default function Controles() {
  const [filtres, setFiltres] = useState({ date: "", conducteur: "", defaut: false });
  const [lignes, setLignes] = useState<Controle[] | null>(null);

  useEffect(() => {
    const p = new URLSearchParams();
    if (filtres.date) p.set("date", filtres.date);
    if (filtres.conducteur) p.set("conducteur", filtres.conducteur);
    if (filtres.defaut) p.set("defaut", "true");
    const t = setTimeout(() => {
      fetch(`/api/admin/controles?${p}`).then(async (r) => {
        if (r.status === 401) return (window.location.href = "/connexion");
        setLignes(await r.json());
      });
    }, 200);
    return () => clearTimeout(t);
  }, [filtres]);

  return (
    <>
      <div className="page-head">
        <div>
          
          <p>Historique des contrôles avant départ, du plus récent au plus ancien.</p>
        </div>
      </div>

      <div className="toolbar">
        <input className="input" type="date" aria-label="Jour" value={filtres.date} onChange={(e) => setFiltres({ ...filtres, date: e.target.value })} />
        <div className="grow">
          <input className="input" type="search" placeholder="Rechercher un conducteur" aria-label="Conducteur" value={filtres.conducteur} onChange={(e) => setFiltres({ ...filtres, conducteur: e.target.value })} />
        </div>
        <label className="check">
          <input type="checkbox" checked={filtres.defaut} onChange={(e) => setFiltres({ ...filtres, defaut: e.target.checked })} />
          Défauts seulement
        </label>
      </div>

      {!lignes ? (
        <p className="muted">Chargement…</p>
      ) : lignes.length === 0 ? (
        <div className="rack-empty"><strong>Aucun contrôle</strong>Aucun contrôle ne correspond à ces filtres.</div>
      ) : (
        <div className="table-wrap">
          <table className="rack rack-cards">
            <thead>
              <tr><th>Date</th><th>Camion</th><th>Conducteur</th><th>Résultat</th><th><span className="sr-only">Ouvrir</span></th></tr>
            </thead>
            <tbody>
              {lignes.map((c) => (
                <tr key={c.id}>
                  <td className="num full muted">{dateHeure(c.created_at)}</td>
                  <td><Plaque size="lg">{c.plaque}</Plaque></td>
                  <td>{c.conducteur}</td>
                  <td>
                    {c.defaut_critique ? <Etat statut="bloque" label="Défaut critique" />
                      : c.has_defaut ? <Etat statut="defaut" label="Défaut" />
                      : <Etat statut="controle" label="Conforme" />}
                  </td>
                  <td className="right"><Link className="btn btn-sm" href={`/admin/controles/${c.id}`} aria-label={`Ouvrir le contrôle de ${c.plaque}`}>Ouvrir</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
