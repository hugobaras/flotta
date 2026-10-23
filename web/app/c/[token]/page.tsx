"use client";

import { Camera, Check, CircleCheck, Eraser, OctagonAlert, Send, TriangleAlert, X } from "lucide-react";
import { use, useEffect, useRef, useState } from "react";
import { Brand, Plaque } from "../../ui";

type Item = { id: number; libelle: string; critique: boolean };
type Controle = { plaque: string; bloque: boolean; checklist: Item[] };
type Resultat = { bloque: boolean; photosManquantes: number };

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
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [photos, setPhotos] = useState<File[]>([]);
  const [signe, setSigne] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [echec, setEchec] = useState("");
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const dessin = useRef(false);

  useEffect(() => {
    fetch(`/api/controle/${token}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status === 409 ? "Aucune checklist n'est configurée pour ce véhicule." : "Ce QR code ne correspond à aucun véhicule."))))
      .then(setData)
      .catch((e) => setErreur(e.message));
  }, [token]);

  if (erreur) {
    return (
      <main className="driver">
        <div className="driver-head"><Brand /></div>
        <div className="alert alert-danger" role="alert"><TriangleAlert aria-hidden /><span>{erreur}</span></div>
      </main>
    );
  }
  if (!data) return <main className="driver"><p className="muted">Chargement…</p></main>;

  if (resultat) {
    return (
      <main className="driver">
        <div className="driver-head"><Brand /></div>
        <div className={`result ${resultat.bloque ? "ko" : "ok"}`} role="status">
          {resultat.bloque ? <OctagonAlert aria-hidden /> : <CircleCheck aria-hidden />}
          <Plaque>{data.plaque}</Plaque>
          <h1>{resultat.bloque ? "Camion bloqué" : "Contrôle enregistré"}</h1>
          <p>{resultat.bloque ? "Un défaut critique a été signalé. Ne prenez pas la route et prévenez votre exploitant." : "Vous pouvez prendre la route. Bonne journée."}</p>
          {resultat.photosManquantes > 0 && <p className="muted">{resultat.photosManquantes} photo(s) n'ont pas pu être envoyées.</p>}
        </div>
      </main>
    );
  }

  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    return [((e.clientX - r.left) * c.width) / r.width, ((e.clientY - r.top) * c.height) / r.height] as const;
  };

  function commencer(e: React.PointerEvent<HTMLCanvasElement>) {
    dessin.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    const ctx = canvas.current!.getContext("2d")!;
    ctx.beginPath();
    ctx.moveTo(...point(e));
  }

  function tracer(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!dessin.current) return;
    const ctx = canvas.current!.getContext("2d")!;
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#14171f";
    ctx.lineTo(...point(e));
    ctx.stroke();
    setSigne(true);
  }

  function effacer() {
    const c = canvas.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    setSigne(false);
  }

  async function envoyer() {
    setEnvoi(true);
    setEchec("");
    try {
      const reponses = data!.checklist.map((i) => ({ id: i.id, ok: !ko[i.id], commentaire: ko[i.id] ? notes[i.id] ?? "" : "" }));
      const pos = await position();
      const r = await fetch(`/api/controle/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conducteur, reponses, signature: signe ? canvas.current!.toDataURL("image/png") : null, ...pos }),
      });
      if (!r.ok) throw new Error();
      const j = await r.json();
      let manque = 0;
      for (const f of photos) {
        const form = new FormData();
        form.append("photo", f);
        if (!(await fetch(`/api/controle/${token}/${j.id}/photos`, { method: "POST", body: form })).ok) manque++;
      }
      setResultat({ bloque: j.bloque, photosManquantes: manque });
    } catch {
      setEchec("L'envoi a échoué. Vérifiez votre réseau puis réessayez : vos réponses sont conservées.");
    }
    setEnvoi(false);
  }

  const nbKo = Object.values(ko).filter(Boolean).length;

  return (
    <main className="driver">
      <div className="driver-head"><Brand /><span className="muted">Contrôle avant départ</span></div>
      <div className="driver-plate">
        <Plaque>{data.plaque}</Plaque>
      </div>

      {data.bloque && (
        <div className="alert alert-danger" role="alert" style={{ marginBottom: 16 }}>
          <OctagonAlert aria-hidden /><span><strong>Ce camion est bloqué.</strong> Un nouveau contrôle ne le débloque pas : contactez votre exploitant.</span>
        </div>
      )}

      <div className="field">
        <label htmlFor="nom" style={{ fontSize: 17 }}>Votre nom</label>
        <input id="nom" className="input" autoComplete="name" value={conducteur} onChange={(e) => setConducteur(e.target.value)} />
      </div>

      <h2>Points à contrôler</h2>
      <ul className="points">
        {data.checklist.map((i) => (
          <li key={i.id} className={`point ${ko[i.id] ? "is-ko" : ""}`}>
            <div className="point-label">
              <span id={`p${i.id}`}>{i.libelle}</span>
              {i.critique && <span className="badge">Critique</span>}
            </div>
            <div className="seg" role="radiogroup" aria-labelledby={`p${i.id}`}>
              <button type="button" role="radio" aria-checked={!ko[i.id]} className="ok" onClick={() => setKo({ ...ko, [i.id]: false })}><Check aria-hidden />OK</button>
              <button type="button" role="radio" aria-checked={!!ko[i.id]} className="ko" onClick={() => setKo({ ...ko, [i.id]: true })}><X aria-hidden />Défaut</button>
            </div>
            {ko[i.id] && (
              <input className="input" aria-label={`Précision sur « ${i.libelle} »`} placeholder="Décrivez le défaut (facultatif)" value={notes[i.id] ?? ""} maxLength={300} onChange={(e) => setNotes({ ...notes, [i.id]: e.target.value })} />
            )}
          </li>
        ))}
      </ul>

      <h2>Photos</h2>
      <label className="file-drop">
        <Camera aria-hidden />
        <span>{photos.length ? `${photos.length} photo${photos.length > 1 ? "s" : ""} ajoutée${photos.length > 1 ? "s" : ""}` : "Prendre ou ajouter des photos"}</span>
        <input type="file" accept="image/jpeg,image/png" multiple onChange={(e) => setPhotos(Array.from(e.target.files ?? []).slice(0, 5))} />
      </label>
      <p className="hint" style={{ marginTop: 6 }}>5 photos au maximum, utiles surtout en cas de défaut.</p>

      <h2>Signature</h2>
      <canvas
        ref={canvas}
        className="signature"
        width={800}
        height={320}
        aria-label="Zone de signature, à dessiner au doigt"
        onPointerDown={commencer}
        onPointerMove={tracer}
        onPointerUp={() => (dessin.current = false)}
        onPointerCancel={() => (dessin.current = false)}
      />
      <button type="button" className="btn btn-sm" style={{ marginTop: 8 }} onClick={effacer} disabled={!signe}><Eraser aria-hidden />Effacer</button>

      {echec && <div className="alert alert-danger" role="alert" style={{ marginTop: 20 }}><TriangleAlert aria-hidden /><span>{echec}</span></div>}

      <div className="submit-bar">
        <div className="inner">
          <button className={`btn btn-xl ${nbKo ? "btn-danger" : "btn-primary"}`} onClick={envoyer} disabled={!conducteur.trim() || envoi}>
            <Send aria-hidden />
            {envoi ? "Envoi en cours…" : nbKo ? `Valider avec ${nbKo} défaut${nbKo > 1 ? "s" : ""}` : "Valider le contrôle"}
          </button>
        </div>
      </div>
    </main>
  );
}
