"use client";

import { useEffect, useState } from "react";

type Offre = { id: string; nom: string; prix_eur: number; minimum_eur: number; inclus: string[] };
const eur = (n: number) => n.toLocaleString("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

export default function GrilleOffres({ courante, action }: { courante?: string; action?: React.ReactNode }) {
  const [data, setData] = useState<{ offres: Offre[]; remise_annuelle_pct: number } | null>(null);
  const [erreur, setErreur] = useState(false);
  useEffect(() => {
    fetch("/api/offres").then(async (r) => (r.ok ? setData(await r.json()) : setErreur(true))).catch(() => setErreur(true));
  }, []);
  if (erreur) return <p className="muted">Les tarifs ne sont pas disponibles pour le moment.</p>;
  if (!data) return <p className="muted" role="status">Chargement des tarifs…</p>;
  return (
    <div>
      <div className="offres">
        {data.offres.map((o) => (
          <section key={o.id} className="offre" aria-labelledby={`offre-${o.id}`}>
            <h3 id={`offre-${o.id}`}>{o.nom}{courante === o.id && <span className="offre-actuelle">Votre offre</span>}</h3>
            <p className="offre-prix"><span className="num">{eur(o.prix_eur)}</span> <span className="muted">par camion et par mois, HT</span></p>
            <p className="hint">Minimum {eur(o.minimum_eur)} par mois</p>
            <ul>{o.inclus.map((i) => <li key={i}>{i}</li>)}</ul>
          </section>
        ))}
      </div>
      <p className="hint" style={{ marginTop: 16 }}>Paiement par virement. {data.remise_annuelle_pct > 0 && `Remise de ${data.remise_annuelle_pct.toLocaleString("fr-FR")} % pour un paiement annuel.`}</p>
      {action}
    </div>
  );
}
