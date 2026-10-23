"use client";

import { useEffect, useState } from "react";
import GrilleOffres from "../../GrilleOffres";
import { ReglagesTabs } from "../../ui";

const STATUTS: Record<string, string> = { essai: "Période d'essai", actif: "Actif", suspendu: "Suspendu" };

export default function MonOffre() {
  const [me, setMe] = useState<{ offre: string; camions_factures: number | null; statut_offre: string | null } | null>(null);
  useEffect(() => {
    fetch("/api/auth/me").then(async (r) => (r.status === 401 ? (window.location.href = "/connexion") : setMe(await r.json())));
  }, []);
  return (
    <>
      <div className="page-head"><div><h1>Réglages</h1>
        {me && <p className="muted">Offre {me.offre === "pro" ? "Pro" : "Essentiel"}{me.camions_factures ? ` · ${me.camions_factures} camions facturés` : ""}{me.statut_offre ? ` · ${STATUTS[me.statut_offre]}` : ""}</p>}
      </div></div>
      <ReglagesTabs actif="offre" />
      <div style={{ marginTop: 24 }}>
        <GrilleOffres courante={me?.offre} action={<p className="hint" style={{ marginTop: 8 }}>Pour changer d'offre ou de nombre de camions, contactez votre interlocuteur Flotta.</p>} />
      </div>
    </>
  );
}
