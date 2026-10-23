"use client";

import { ChevronRight, ClipboardCheck, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { dateHeure, Empty, Plaque } from "../../ui";

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
      <div className="page-header">
        <div>
          <h1>Contrôles</h1>
          <p>Historique des contrôles avant départ, du plus récent au plus ancien.</p>
        </div>
      </div>

      <div className="toolbar">
        <input className="input" type="date" aria-label="Jour" value={filtres.date} onChange={(e) => setFiltres({ ...filtres, date: e.target.value })} />
        <div className="input-icon grow">
          <Search aria-hidden />
          <input className="input" type="search" placeholder="Rechercher un conducteur" aria-label="Conducteur" value={filtres.conducteur} onChange={(e) => setFiltres({ ...filtres, conducteur: e.target.value })} />
        </div>
        <label className="switch">
          <input type="checkbox" role="switch" checked={filtres.defaut} onChange={(e) => setFiltres({ ...filtres, defaut: e.target.checked })} />
          Défauts seulement
        </label>
      </div>

      <div className="panel">
        {!lignes ? (
          <p className="muted" style={{ padding: 24 }}>Chargement…</p>
        ) : lignes.length === 0 ? (
          <Empty icon={<ClipboardCheck aria-hidden />} title="Aucun contrôle">Aucun contrôle ne correspond à ces filtres.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table table-cards">
              <thead>
                <tr><th>Date</th><th>Camion</th><th>Conducteur</th><th>Résultat</th><th><span className="sr-only">Voir</span></th></tr>
              </thead>
              <tbody>
                {lignes.map((c) => (
                  <tr key={c.id}>
                    <td className="num full muted">{dateHeure(c.created_at)}</td>
                    <td><Plaque>{c.plaque}</Plaque></td>
                    <td>{c.conducteur}</td>
                    <td>
                      {c.defaut_critique ? <span className="badge badge-danger">Défaut critique</span>
                        : c.has_defaut ? <span className="badge badge-warn">Défaut</span>
                        : <span className="badge badge-ok">Conforme</span>}
                    </td>
                    <td className="right"><Link className="btn btn-ghost btn-icon" href={`/admin/controles/${c.id}`} aria-label={`Ouvrir le contrôle de ${c.plaque}`}><ChevronRight aria-hidden /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
