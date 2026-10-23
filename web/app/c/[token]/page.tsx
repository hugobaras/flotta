"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { enAttente, envoyerUn, mettreEnFile, transitoire, viderLaFile } from "../../lib/offline";
import { BandeauPublic, Etat, Macaron, Plaque } from "../../ui";

type Item = { id: number; libelle: string; critique: boolean };
type Controle = { plaque: string; bloque: boolean; checklist: Item[] };
type Resultat = { bloque: boolean; photosManquantes: number; enAttente?: boolean };
type Identite = { nom: string; badge: string; expire: number };

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
const CLE_BADGE = "flotta-badge";
const lire = (cle: string) => {
  try { return localStorage.getItem(cle) ?? ""; } catch { return ""; }
};
const ecrire = (cle: string, valeur: string | null) => {
  try { valeur === null ? localStorage.removeItem(cle) : localStorage.setItem(cle, valeur); } catch { /* navigation privée : on ne garde rien */ }
};

export default function Controle({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<Controle | null>(null);
  const [erreur, setErreur] = useState("");
  const [identite, setIdentite] = useState<Identite | null>(null);
  const [pin, setPin] = useState("");
  const [erreurPin, setErreurPin] = useState("");
  const [saisieNom, setSaisieNom] = useState(false);
  const [nom, setNom] = useState("");
  const [etape, setEtape] = useState(0); // 0 = identification, 1..n = points, n + 1 = signature et envoi
  const [rep, setRep] = useState<Record<number, "ok" | "ko">>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [photos, setPhotos] = useState<File[]>([]);
  const [signe, setSigne] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [echec, setEchec] = useState("");
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const [attente, setAttente] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const dessin = useRef(false);
  const clientId = useRef("");

  const synchroniser = useCallback(async () => {
    try {
      const { restants } = await viderLaFile();
      setAttente(restants);
    } catch {
      /* IndexedDB indisponible : rien à synchroniser */
    }
  }, []);

  useEffect(() => {
    setNom(lire(CLE_NOM));
    try {
      const b: Identite | null = JSON.parse(lire(CLE_BADGE) || "null");
      if (b && b.expire * 1000 > Date.now()) setIdentite(b);
    } catch { /* badge illisible : on redemande le code */ }
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    enAttente().then((l) => setAttente(l.length)).catch(() => undefined);
    synchroniser();
    window.addEventListener("online", synchroniser);
    return () => window.removeEventListener("online", synchroniser);
  }, [synchroniser]);

  useEffect(() => {
    fetch(`/api/controle/${token}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status === 409 ? "Aucune checklist n'est configurée pour ce véhicule." : "Ce QR code ne correspond à aucun véhicule."))))
      .then(setData)
      .catch((e) => setErreur(e instanceof TypeError ? "Pas de réseau et ce camion n'a jamais été ouvert sur ce téléphone." : e.message));
  }, [token]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [etape]);

  const bandeauAttente = attente > 0 && (
    <div className="notice" role="status">
      <span><strong>{attente} contrôle{attente > 1 ? "s" : ""} en attente d'envoi.</strong> Il sera envoyé dès que le réseau revient.</span>{" "}
      <button className="link-btn" onClick={synchroniser}>Envoyer maintenant</button>
    </div>
  );

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
          {bandeauAttente}
          <div className="result" role="status">
            <Macaron statut={resultat.enAttente ? "non_controle" : resultat.bloque ? "bloque" : "controle"} size="xl" />
            <Plaque size="xl">{data.plaque}</Plaque>
            <h1>{resultat.enAttente ? "Enregistré sur ce téléphone" : resultat.bloque ? "Camion bloqué" : "Contrôle enregistré"}</h1>
            <p>
              {resultat.enAttente
                ? "Pas de réseau pour le moment. Votre contrôle sera envoyé automatiquement dès que la connexion revient. Gardez cette page ouverte ou rouvrez-la plus tard."
                : resultat.bloque ? "Un défaut critique a été signalé. Ne prenez pas la route et prévenez votre exploitant." : "Vous pouvez prendre la route. Bonne journée."}
            </p>
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
  const nomAffiche = identite?.nom ?? nom.trim();

  async function identifier(e: React.FormEvent) {
    e.preventDefault();
    setErreurPin("");
    try {
      const r = await fetch(`/api/controle/${token}/identifier`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin }) });
      if (r.status === 429) return setErreurPin("Trop d'essais. Réessayez dans quelques minutes ou saisissez votre nom.");
      if (!r.ok) return setErreurPin("Code inconnu. Vérifiez votre code ou saisissez votre nom.");
      const j: Identite = await r.json();
      ecrire(CLE_BADGE, JSON.stringify(j));
      setIdentite(j);
      setEtape(1);
    } catch {
      setSaisieNom(true);
      setErreurPin("Pas de réseau : saisissez votre nom pour continuer.");
    }
  }

  function commencerAvecNom(e: React.FormEvent) {
    e.preventDefault();
    if (!nom.trim()) return setErreurPin("Indiquez votre nom pour commencer.");
    ecrire(CLE_NOM, nom.trim());
    setEtape(1);
  }

  function pasMoi() {
    ecrire(CLE_BADGE, null);
    setIdentite(null);
    setPin("");
  }

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
    if (!clientId.current) clientId.current = crypto.randomUUID(); // le même identifiant à chaque nouvel essai : pas de doublon
    const pos = await position();
    const payload = {
      ...(identite ? { badge: identite.badge } : { conducteur: nom.trim() }),
      reponses: data!.checklist.map((i) => ({ id: i.id, ok: rep[i.id] !== "ko", commentaire: rep[i.id] === "ko" ? notes[i.id] ?? "" : "" })),
      signature: signe ? canvas.current!.toDataURL("image/png") : null,
      fait_le: new Date().toISOString(),
      ...pos,
    };
    const envoiPrepare = { client_id: clientId.current, token, payload, photos: photos as Blob[], cree: Date.now() };
    try {
      const j = await envoyerUn(envoiPrepare);
      setResultat({ bloque: j.bloque, photosManquantes: j.photosManquantes });
    } catch (e) {
      const statut = (e as { statut?: number }).statut;
      if (transitoire(e, statut)) {
        try {
          await mettreEnFile(envoiPrepare);
          setAttente((await enAttente()).length);
          setResultat({ bloque: false, photosManquantes: 0, enAttente: true });
        } catch {
          setEchec("Pas de réseau et impossible d'enregistrer sur ce téléphone. Réessayez avec du réseau.");
        }
      } else if (statut === 401) {
        ecrire(CLE_BADGE, null);
        setIdentite(null);
        setEtape(0);
        setErreurPin("Votre identification a expiré : saisissez de nouveau votre code.");
      } else {
        setEchec("L'envoi a échoué. Réessayez : vos réponses sont conservées.");
      }
    }
    setEnvoi(false);
  }

  const progression = (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={n} aria-valuenow={Math.min(etape, n)} aria-label="Avancement du contrôle">
      <span style={{ width: `${(Math.min(etape - 1, n) / n) * 100}%` }} />
    </div>
  );

  // Étape 0 : qui contrôle ? Un code à 4 chiffres, ou le nom à la main si le réseau manque.
  if (etape === 0) {
    return (
      <>
        <BandeauPublic />
        <main className="driver">
          {bandeauAttente}
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
          {identite ? (
            <div className="stack-form">
              <p style={{ fontSize: 20 }}>Bonjour <strong>{identite.nom}</strong></p>
              <button className="btn btn-primary btn-xl" onClick={() => setEtape(1)}>Commencer ({data.checklist.length} points)</button>
              <button className="link-btn" onClick={pasMoi} style={{ justifySelf: "start" }}>Ce n'est pas moi</button>
            </div>
          ) : saisieNom ? (
            <form onSubmit={commencerAvecNom} className="stack-form">
              <div className="field">
                <label htmlFor="nom">Votre nom</label>
                <input id="nom" className="input" autoComplete="name" value={nom} onChange={(e) => { setNom(e.target.value); setErreurPin(""); }} autoFocus />
              </div>
              {erreurPin && <p role="alert" style={{ color: "var(--rouge)", fontWeight: 500 }}>{erreurPin}</p>}
              <button className="btn btn-primary btn-xl" type="submit">Commencer ({data.checklist.length} points)</button>
              <button type="button" className="link-btn" onClick={() => { setSaisieNom(false); setErreurPin(""); }} style={{ justifySelf: "start" }}>J'ai un code</button>
            </form>
          ) : (
            <form onSubmit={identifier} className="stack-form">
              <div className="field">
                <label htmlFor="pin">Votre code à 4 chiffres</label>
                <input id="pin" className="input pin-input" inputMode="numeric" autoComplete="off" pattern="\d{4}" maxLength={4} value={pin} onChange={(e) => { setPin(e.target.value.replace(/\D/g, "")); setErreurPin(""); }} aria-invalid={!!erreurPin} aria-describedby={erreurPin ? "pin-erreur" : undefined} autoFocus />
                {erreurPin && <p id="pin-erreur" role="alert" style={{ color: "var(--rouge)", fontWeight: 500 }}>{erreurPin}</p>}
              </div>
              <button className="btn btn-primary btn-xl" type="submit" disabled={pin.length !== 4}>Continuer</button>
              <button type="button" className="link-btn" onClick={() => { setSaisieNom(true); setErreurPin(""); }} style={{ justifySelf: "start" }}>Je n'ai pas de code : saisir mon nom</button>
            </form>
          )}
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
          {nomAffiche && <>{nomAffiche} · </>}{nbOk} point{nbOk > 1 ? "s" : ""} OK{defauts.length > 0 && <>, <strong style={{ color: "var(--rouge)" }}>{defauts.length} défaut{defauts.length > 1 ? "s" : ""}</strong></>}
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
