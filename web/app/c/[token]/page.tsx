"use client";

import { use, useEffect, useRef, useState } from "react";
import { BandeauPublic, Etat, Macaron, Plaque } from "../../ui";

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

const CLE_NOM = "flotta-nom";
const lireNom = () => {
  try { return localStorage.getItem(CLE_NOM) ?? ""; } catch { return ""; }
};
const garderNom = (n: string) => {
  try { localStorage.setItem(CLE_NOM, n); } catch { /* navigation privée : on ne garde rien */ }
};

export default function Controle({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<Controle | null>(null);
  const [erreur, setErreur] = useState("");
  const [conducteur, setConducteur] = useState("");
  const [etape, setEtape] = useState(0); // 0 = nom, 1..n = points, n + 1 = signature et envoi
  const [rep, setRep] = useState<Record<number, "ok" | "ko">>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [photos, setPhotos] = useState<File[]>([]);
  const [signe, setSigne] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [echec, setEchec] = useState("");
  const [erreurNom, setErreurNom] = useState("");
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const dessin = useRef(false);

  useEffect(() => {
    setConducteur(lireNom());
  }, []);

  useEffect(() => {
    fetch(`/api/controle/${token}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status === 409 ? "Aucune checklist n'est configurée pour ce véhicule." : "Ce QR code ne correspond à aucun véhicule."))))
      .then(setData)
      .catch((e) => setErreur(e.message));
  }, [token]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [etape]);

  if (erreur) {
    return (
      <>
        <BandeauPublic />
        <main className="driver"><div className="notice danger" role="alert">{erreur}</div></main>
      </>
    );
  }
  if (!data) return <><BandeauPublic /><main className="driver"><p className="muted">Chargement…</p></main></>;

  if (resultat) {
    return (
      <>
        <BandeauPublic />
        <main className="driver">
          <div className="result" role="status">
            <Macaron statut={resultat.bloque ? "bloque" : "controle"} size="xl" />
            <Plaque size="xl">{data.plaque}</Plaque>
            <h1>{resultat.bloque ? "Camion bloqué" : "Contrôle enregistré"}</h1>
            <p>{resultat.bloque ? "Un défaut critique a été signalé. Ne prenez pas la route et prévenez votre exploitant." : "Vous pouvez prendre la route. Bonne journée."}</p>
            {resultat.photosManquantes > 0 && <p className="muted">{resultat.photosManquantes} photo(s) n'ont pas pu être envoyées.</p>}
          </div>
        </main>
      </>
    );
  }

  const n = data.checklist.length;
  const fin = n + 1;
  const point = etape >= 1 && etape <= n ? data.checklist[etape - 1] : null;
  const defauts = data.checklist.filter((i) => rep[i.id] === "ko");
  const nbOk = data.checklist.filter((i) => rep[i.id] === "ok").length;

  function repondre(i: Item, r: "ok" | "ko") {
    setRep({ ...rep, [i.id]: r });
    if (r === "ok") setEtape(etape + 1);
  }

  function toutLeResteOk() {
    const suite = { ...rep };
    for (const i of data!.checklist) if (!suite[i.id]) suite[i.id] = "ok";
    setRep(suite);
    setEtape(fin);
  }

  function commencer(e: React.FormEvent) {
    e.preventDefault();
    if (!conducteur.trim()) return setErreurNom("Indiquez votre nom pour commencer.");
    garderNom(conducteur.trim());
    setEtape(1);
  }

  const pt = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    return [((e.clientX - r.left) * c.width) / r.width, ((e.clientY - r.top) * c.height) / r.height] as const;
  };

  function commencerTrait(e: React.PointerEvent<HTMLCanvasElement>) {
    dessin.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    const ctx = canvas.current!.getContext("2d")!;
    ctx.beginPath();
    ctx.moveTo(...pt(e));
  }

  function tracer(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!dessin.current) return;
    const ctx = canvas.current!.getContext("2d")!;
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#111418";
    ctx.lineTo(...pt(e));
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
      const reponses = data!.checklist.map((i) => ({ id: i.id, ok: rep[i.id] !== "ko", commentaire: rep[i.id] === "ko" ? notes[i.id] ?? "" : "" }));
      const pos = await position();
      const r = await fetch(`/api/controle/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conducteur: conducteur.trim(), reponses, signature: signe ? canvas.current!.toDataURL("image/png") : null, ...pos }),
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

  const progression = (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={n} aria-valuenow={Math.min(etape, n)} aria-label="Avancement du contrôle">
      <span style={{ width: `${(Math.min(etape - 1, n) / n) * 100}%` }} />
    </div>
  );

  // Étape 0 : qui contrôle.
  if (etape === 0) {
    return (
      <>
        <BandeauPublic />
        <main className="driver">
          <div className="driver-id">
            <Plaque size="xl">{data.plaque}</Plaque>
            {data.bloque && <Etat statut="bloque" />}
          </div>
          <h1>Contrôle avant départ</h1>
          {data.bloque && (
            <div className="notice danger" role="alert">
              <span><strong>Ce camion est bloqué.</strong> Un nouveau contrôle ne le débloque pas : contactez votre exploitant.</span>
            </div>
          )}
          <form onSubmit={commencer} className="stack-form">
            <div className="field">
              <label htmlFor="nom">Votre nom</label>
              <input id="nom" className="input" autoComplete="name" value={conducteur} aria-invalid={!!erreurNom} aria-describedby={erreurNom ? "nom-erreur" : undefined} onChange={(e) => { setConducteur(e.target.value); setErreurNom(""); }} />
              {erreurNom && <p id="nom-erreur" role="alert" style={{ color: "var(--rouge)", fontWeight: 500 }}>{erreurNom}</p>}
            </div>
            <button className="btn btn-primary btn-xl" type="submit">Commencer ({n} points)</button>
          </form>
        </main>
      </>
    );
  }

  // Étape par point : une question, deux gros boutons.
  if (point) {
    const choix = rep[point.id];
    return (
      <>
        <BandeauPublic />
        <main className="driver">
          <div className="step-head">
            <Plaque>{data.plaque}</Plaque>
            <span className="muted">Point {etape} sur {n}</span>
          </div>
          {progression}
          <h1 className="question">{point.libelle}</h1>
          {point.critique && <p className="muted" style={{ marginBottom: 20 }}>Point critique : un défaut bloque le camion.</p>}

          <div className="big-seg" role="radiogroup" aria-label={point.libelle}>
            <button type="button" role="radio" aria-checked={choix === "ok"} className="ok" onClick={() => repondre(point, "ok")}>OK</button>
            <button type="button" role="radio" aria-checked={choix === "ko"} className="ko" onClick={() => repondre(point, "ko")}>Défaut</button>
          </div>

          {choix === "ko" && (
            <div className="defaut-detail">
              <div className="field">
                <label htmlFor="precision">Décrivez le défaut (facultatif)</label>
                <input id="precision" className="input" value={notes[point.id] ?? ""} maxLength={300} onChange={(e) => setNotes({ ...notes, [point.id]: e.target.value })} autoFocus />
              </div>
              <label className="file-drop">
                <span>{photos.length ? `${photos.length} photo${photos.length > 1 ? "s" : ""} ajoutée${photos.length > 1 ? "s" : ""} : en ajouter` : "Ajouter une photo"}</span>
                <input type="file" accept="image/jpeg,image/png" capture="environment" disabled={photos.length >= 5} onChange={(e) => { const f = e.target.files?.[0]; if (f) setPhotos([...photos, f].slice(0, 5)); e.target.value = ""; }} />
              </label>
              <button className="btn btn-primary btn-xl" onClick={() => setEtape(etape + 1)}>Continuer</button>
            </div>
          )}

          <div className="step-foot">
            <button className="link-btn" onClick={() => setEtape(etape - 1)}>Précédent</button>
            <button className="link-btn" onClick={toutLeResteOk}>{etape === 1 && !Object.keys(rep).length ? "Tout est OK" : "Tout le reste est OK"}</button>
          </div>
        </main>
      </>
    );
  }

  // Dernière étape : récapitulatif, signature, envoi.
  return (
    <>
      <BandeauPublic />
      <main className="driver">
        <div className="step-head">
          <Plaque>{data.plaque}</Plaque>
          <span className="muted">Dernière étape</span>
        </div>
        <h1 className="question">Signez pour valider</h1>
        <p className="recap">
          {nbOk} point{nbOk > 1 ? "s" : ""} OK{defauts.length > 0 && <>, <strong style={{ color: "var(--rouge)" }}>{defauts.length} défaut{defauts.length > 1 ? "s" : ""}</strong></>}
        </p>
        {defauts.length > 0 && (
          <ul className="recap-list">
            {defauts.map((i) => <li key={i.id}>{i.libelle}{notes[i.id] ? <span className="muted"> · {notes[i.id]}</span> : null}</li>)}
          </ul>
        )}

        <div className="signature-wrap">
          <canvas
            ref={canvas}
            className="signature"
            width={800}
            height={340}
            aria-label="Zone de signature, à dessiner au doigt"
            onPointerDown={commencerTrait}
            onPointerMove={tracer}
            onPointerUp={() => (dessin.current = false)}
            onPointerCancel={() => (dessin.current = false)}
          />
          <button type="button" className="link-btn" onClick={effacer} disabled={!signe}>Effacer</button>
        </div>

        {echec && <div className="notice danger" role="alert" style={{ marginTop: 20 }}>{echec}</div>}

        <div className="step-foot">
          <button className="link-btn" onClick={() => setEtape(n)}>Précédent</button>
        </div>

        <div className="submit-bar">
          <div className="inner">
            <button className={`btn btn-xl ${defauts.length ? "btn-danger" : "btn-primary"}`} onClick={envoyer} disabled={envoi}>
              {envoi ? "Envoi en cours…" : defauts.length ? `Valider avec ${defauts.length} défaut${defauts.length > 1 ? "s" : ""}` : "Valider le contrôle"}
            </button>
          </div>
        </div>
      </main>
    </>
  );
}
