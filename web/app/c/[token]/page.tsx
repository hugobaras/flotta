"use client";

import { use, useEffect, useRef, useState } from "react";

type Item = { id: number; libelle: string; critique: boolean };
type Controle = { plaque: string; bloque: boolean; checklist: Item[] };

function position(): Promise<{ lat: number; lng: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { timeout: 5000 },
    );
  });
}

export default function Controle({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<Controle | null>(null);
  const [erreur, setErreur] = useState("");
  const [conducteur, setConducteur] = useState("");
  const [ko, setKo] = useState<Record<number, boolean>>({});
  const [photos, setPhotos] = useState<File[]>([]);
  const [signe, setSigne] = useState(false);
  const [resultat, setResultat] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  const dessin = useRef(false);

  useEffect(() => {
    fetch(`/api/controle/${token}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status === 409 ? "Aucune checklist configurée pour ce véhicule." : "Véhicule inconnu"))))
      .then(setData)
      .catch((e) => setErreur(e.message));
  }, [token]);

  if (erreur) return <p role="alert">{erreur}</p>;
  if (!data) return <p>Chargement…</p>;

  function tracer(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!dessin.current) return;
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    const ctx = c.getContext("2d")!;
    ctx.lineWidth = 2;
    ctx.lineTo(((e.clientX - r.left) * c.width) / r.width, ((e.clientY - r.top) * c.height) / r.height);
    ctx.stroke();
    setSigne(true);
  }

  function effacer() {
    const c = canvas.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    setSigne(false);
  }

  async function envoyer() {
    const reponses = data!.checklist.map((i) => ({ id: i.id, ok: !ko[i.id] }));
    const pos = await position();
    const r = await fetch(`/api/controle/${token}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conducteur, reponses, signature: signe ? canvas.current!.toDataURL("image/png") : null, ...pos }),
    });
    if (!r.ok) return setResultat("Échec de l'envoi, réessayez.");
    const j = await r.json();
    let manque = 0;
    for (const f of photos) {
      const form = new FormData();
      form.append("photo", f);
      if (!(await fetch(`/api/controle/${token}/${j.id}/photos`, { method: "POST", body: form })).ok) manque++;
    }
    setResultat(
      (j.bloque ? "Défaut critique : véhicule bloqué, prévenez l'exploitant." : "Contrôle enregistré.") +
        (manque ? ` ${manque} photo(s) non envoyée(s).` : ""),
    );
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
      <p>
        <label>
          Photos (5 maximum){" "}
          <input type="file" accept="image/jpeg,image/png" multiple capture="environment" onChange={(e) => setPhotos(Array.from(e.target.files ?? []).slice(0, 5))} />
        </label>
      </p>
      <p>Signature :</p>
      <canvas
        ref={canvas}
        width={400}
        height={160}
        style={{ border: "1px solid #888", width: "100%", touchAction: "none" }}
        onPointerDown={(e) => { dessin.current = true; const c = canvas.current!; const r = c.getBoundingClientRect(); c.getContext("2d")!.beginPath(); c.getContext("2d")!.moveTo(((e.clientX - r.left) * c.width) / r.width, ((e.clientY - r.top) * c.height) / r.height); }}
        onPointerMove={tracer}
        onPointerUp={() => (dessin.current = false)}
        onPointerLeave={() => (dessin.current = false)}
      />
      <button type="button" onClick={effacer}>Effacer la signature</button>
      <p>
        <button onClick={envoyer} disabled={!conducteur.trim()}>Valider le contrôle</button>
      </p>
      {resultat && <p>{resultat}</p>}
    </main>
  );
}
