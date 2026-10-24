"use client";

import { useCallback, useEffect, useState } from "react";
import { Coche } from "../../ui";

type Etape = { id: string; titre: string; lien: string; fait: boolean | null; aide: string };
const GUIDES = [
  ["controle-depart", "Contrôle avant départ"],
  ["flotte-commandes", "Flotte et commandes"],
  ["planification", "Planification des tournées"],
  ["chauffeur", "Côté chauffeur"],
];

export default function Demarrer() {
  const [d, setD] = useState<{ demo: boolean; etapes: Etape[] } | null>(null);
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    const r = await fetch("/api/admin/demarrage");
    if (r.status === 401) return (window.location.href = "/connexion");
    setD(await r.json());
  }, []);
  useEffect(() => { charger(); }, [charger]);

  async function demo(activer: boolean) {
    setErreur("");
    if (!activer && !window.confirm("Supprimer les camions, conducteurs et commandes de démonstration ?")) return;
    const r = await fetch("/api/admin/demo", { method: activer ? "POST" : "DELETE" });
    if (!r.ok) setErreur((await r.json().catch(() => ({}))).detail ?? "Action impossible.");
    charger();
  }

  const faites = d?.etapes.filter((e) => e.fait).length ?? 0;
  return (
    <>
      <div className="page-head"><div><p className="muted">Six étapes pour être opérationnel. {d && `${faites} faite${faites > 1 ? "s" : ""} sur ${d.etapes.filter((e) => e.fait !== null).length} vérifiables.`}</p></div></div>
      {erreur && <div className="notice danger" role="alert">{erreur}</div>}
      <ol className="demarrage">
        {d?.etapes.map((e) => (
          <li key={e.id}>
            <span aria-hidden>{e.fait ? <Coche ok /> : <span className="rond" />}</span>
            <div style={{ flex: 1 }}>
              <strong>{e.titre}</strong>{e.fait && <span className="muted"> · fait</span>}
              <p className="muted">{e.aide}</p>
            </div>
            <a className={e.fait ? "btn btn-sm" : "btn btn-primary btn-sm"} href={e.lien}>{e.fait ? "Ouvrir" : "Commencer"}</a>
          </li>
        ))}
      </ol>
      <section style={{ marginTop: 40 }}>
        <h2>Essayer avec des données fictives</h2>
        <p className="muted" style={{ margin: "6px 0 12px", maxWidth: "40em" }}>Ajoute 15 camions, 15 conducteurs, un dépôt et 80 commandes du jour localisées autour de Nantes, pour tester le planning sans rien saisir. Tout se supprime en un clic.</p>
        {d && (d.demo
          ? <button className="btn" onClick={() => demo(false)}>Supprimer les données de démonstration</button>
          : <button className="btn btn-primary" onClick={() => demo(true)}>Charger les données de démonstration</button>)}
      </section>
      <section style={{ marginTop: 40 }}>
        <h2>Guides (PDF, une page)</h2>
        <ul className="liste" style={{ marginTop: 8 }}>
          {GUIDES.map(([f, t]) => <li key={f} style={{ padding: "8px 0" }}><a href={`/aide/${f}.pdf`} target="_blank" rel="noreferrer">{t}</a></li>)}
        </ul>
      </section>
    </>
  );
}
