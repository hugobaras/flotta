"use client";

import { use, useEffect, useState } from "react";

type Item = { id: number; libelle: string; critique: boolean };
type Controle = { plaque: string; bloque: boolean; checklist: Item[] };

export default function Controle({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<Controle | null>(null);
  const [erreur, setErreur] = useState("");
  const [conducteur, setConducteur] = useState("");
  const [ko, setKo] = useState<Record<number, boolean>>({});
  const [resultat, setResultat] = useState("");

  useEffect(() => {
    fetch(`/api/controle/${token}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Véhicule inconnu"))))
      .then(setData)
      .catch((e) => setErreur(e.message));
  }, [token]);

  if (erreur) return <p role="alert">{erreur}</p>;
  if (!data) return <p>Chargement…</p>;

  async function envoyer() {
    const reponses = data!.checklist.map((i) => ({ id: i.id, ok: !ko[i.id] }));
    const r = await fetch(`/api/controle/${token}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conducteur, reponses }),
    });
    if (!r.ok) return setResultat("Échec de l'envoi, réessayez.");
    const j = await r.json();
    setResultat(j.bloque ? "Défaut critique : véhicule bloqué, prévenez l'exploitant." : "Contrôle enregistré.");
  }

  return (
    <main>
      <h1>{data.plaque}</h1>
      {data.bloque && <p role="alert">Ce véhicule est bloqué.</p>}
      <input placeholder="Votre nom" value={conducteur} onChange={(e) => setConducteur(e.target.value)} />
      <ul style={{ listStyle: "none", padding: 0 }}>
        {data.checklist.map((i) => (
          <li key={i.id}>
            <label>
              <input type="checkbox" checked={!!ko[i.id]} onChange={(e) => setKo({ ...ko, [i.id]: e.target.checked })} />{" "}
              Défaut : {i.libelle}
              {i.critique && " (critique)"}
            </label>
          </li>
        ))}
      </ul>
      <button onClick={envoyer} disabled={!conducteur.trim()}>Valider le contrôle</button>
      {resultat && <p>{resultat}</p>}
    </main>
  );
}
