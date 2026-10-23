"use client";

import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { enAttente, Envoi, envoyerUn, mettreEnFile, transitoire, viderLaFile } from "../../lib/offline";
import { BandeauPublic, Plaque } from "../../ui";

type Arret = {
  order_id: number; ordre: number; reference: string; client: string; adresse: string; lat: number | null; lng: number | null; arrivee_min: number;
  fenetre_debut: string | null; fenetre_fin: string | null; palettes: number; poids_kg: number; contact_nom: string; contact_telephone: string; consignes: string;
  statut: "arrive" | "livre" | "impossible" | null; motif: string | null;
};
type Tournee = {
  plaque: string; jour: string; conducteur: string | null; verrouillee: boolean; raison: string | null; controle_token: string; jour_du_plan: boolean;
  motifs: Record<string, string>; arrets: Arret[]; depart_min?: number; retour_min?: number; distance_km?: number;
};

const hhmm = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(Math.round(m % 60)).padStart(2, "0")}`;
const FINAUX = ["livre", "impossible"];

function position(): Promise<{ lat: number; lng: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition((p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }), () => resolve(null), { timeout: 4000 });
  });
}

export default function MaTournee({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [t, setT] = useState<Tournee | null>(null);
  const [erreur, setErreur] = useState("");
  const [locaux, setLocaux] = useState<Record<number, Arret["statut"]>>({}); // statuts envoyés depuis ce téléphone, y compris hors ligne
  const [attente, setAttente] = useState(0);
  const [ouvert, setOuvert] = useState<number | null>(null);
  const [mode, setMode] = useState<"livre" | "impossible" | null>(null);
  const [destinataire, setDestinataire] = useState("");
  const [motif, setMotif] = useState("absent");
  const [commentaire, setCommentaire] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [signe, setSigne] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [message, setMessage] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  const dessin = useRef(false);

  const charger = useCallback(async () => {
    try {
      const r = await fetch(`/api/tournee/${token}`);
      if (r.status === 410) return setErreur((await r.json()).detail);
      if (!r.ok) return setErreur("Ce lien de tournée est inconnu. Demandez-en un nouveau à votre exploitant.");
      setT(await r.json());
    } catch {
      setErreur("Pas de réseau et cette tournée n'a jamais été ouverte sur ce téléphone.");
    }
  }, [token]);

  const synchroniser = useCallback(async () => {
    try {
      const { restants } = await viderLaFile();
      const restantes = (await enAttente()).filter((e) => e.type === "livraison" && e.token === token);
      setAttente(restantes.length);
      if (!restantes.length) setLocaux({});
      charger();
    } catch { /* IndexedDB indisponible */ }
  }, [charger, token]);

  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    charger();
    // Statuts déjà saisis mais pas encore envoyés : on les réaffiche.
    enAttente().then((l) => {
      const mine = l.filter((e) => e.type === "livraison" && e.token === token);
      setAttente(mine.length);
      setLocaux(Object.fromEntries(mine.map((e) => [e.payload.order_id as number, e.payload.statut as Arret["statut"]])));
    }).catch(() => undefined);
    synchroniser();
    window.addEventListener("online", synchroniser);
    return () => window.removeEventListener("online", synchroniser);
  }, [charger, synchroniser, token]);

  const arrets = useMemo(() => (t?.arrets ?? []).map((a) => ({ ...a, statut: (FINAUX.includes(a.statut ?? "") ? a.statut : locaux[a.order_id] ?? a.statut) as Arret["statut"] })), [t, locaux]);
  const courant = arrets.find((a) => !FINAUX.includes(a.statut ?? ""));
  const faits = arrets.filter((a) => FINAUX.includes(a.statut ?? "")).length;

  async function envoyer(a: Arret, statut: "arrive" | "livre" | "impossible", extra: Record<string, unknown> = {}, fichiers: File[] = []) {
    setEnvoi(true);
    setMessage("");
    const pos = await position();
    const e: Envoi = {
      type: "livraison", client_id: crypto.randomUUID(), token, cree: Date.now(), photos: fichiers as Blob[],
      payload: { order_id: a.order_id, statut, fait_le: new Date().toISOString(), ...pos, ...extra },
    };
    setLocaux((l) => ({ ...l, [a.order_id]: statut })); // affichage immédiat, même sans réseau
    try {
      await envoyerUn(e);
      setLocaux((l) => { const n = { ...l }; delete n[a.order_id]; return n; });
      charger();
    } catch (err) {
      const code = (err as { statut?: number }).statut;
      if (transitoire(err, code)) {
        await mettreEnFile(e);
        setAttente((await enAttente()).filter((x) => x.type === "livraison" && x.token === token).length);
      } else {
        setLocaux((l) => { const n = { ...l }; delete n[a.order_id]; return n; });
        setMessage(code === 409 ? "Cet arrêt est déjà clôturé ou la tournée est verrouillée." : "L'envoi a échoué. Réessayez.");
      }
    }
    setEnvoi(false);
  }

  const pt = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    return [((e.clientX - r.left) * c.width) / r.width, ((e.clientY - r.top) * c.height) / r.height] as const;
  };

  async function confirmer(a: Arret) {
    if (mode === "livre") {
      await envoyer(a, "livre", { nom_destinataire: destinataire || null, signature: signe ? canvas.current!.toDataURL("image/png") : null }, photos);
    } else if (mode === "impossible") {
      await envoyer(a, "impossible", { motif, commentaire: commentaire || null }, photos);
    }
    setMode(null); setDestinataire(""); setCommentaire(""); setPhotos([]); setSigne(false); setOuvert(null);
  }

  const bandeau = attente > 0 && (
    <div className="notice" role="status">
      <span><strong>{attente} envoi{attente > 1 ? "s" : ""} en attente.</strong> Ils partiront dès que le réseau revient.</span> <button className="link-btn" onClick={synchroniser}>Envoyer maintenant</button>
    </div>
  );

  if (erreur) return <><BandeauPublic /><main className="driver"><div className="notice danger" role="alert">{erreur}</div></main></>;
  if (!t) return <><BandeauPublic /><main className="driver"><p className="muted">Chargement…</p></main></>;

  if (t.verrouillee) {
    return (
      <>
        <BandeauPublic />
        <main className="driver">
          <div className="driver-id"><Plaque size="xl">{t.plaque}</Plaque></div>
          <h1>Ma tournée</h1>
          <div className="notice danger" role="alert"><span><strong>Tournée verrouillée.</strong> {t.raison}</span></div>
          <a className="btn btn-primary btn-xl" href={`/c/${t.controle_token}`}>Faire le contrôle avant départ</a>
          <button className="link-btn" style={{ marginTop: 16 }} onClick={charger}>J'ai fait le contrôle : actualiser</button>
        </main>
      </>
    );
  }

  return (
    <>
      <BandeauPublic />
      <main className="driver">
        <div className="driver-id"><Plaque size="xl">{t.plaque}</Plaque><span className="muted">{faits} sur {arrets.length}</span></div>
        <h1>Ma tournée</h1>
        <p className="muted" style={{ marginBottom: 16 }}>
          {new Date(t.jour).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}{t.conducteur ? ` · ${t.conducteur}` : ""}
          {t.depart_min !== undefined && ` · départ ${hhmm(t.depart_min)}`}
        </p>
        {!t.jour_du_plan && <div className="notice" role="status">Cette tournée n'est pas celle d'aujourd'hui.</div>}
        {bandeau}
        {message && <div className="notice danger" role="alert">{message}</div>}
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={arrets.length} aria-valuenow={faits} aria-label="Arrêts terminés"><span style={{ width: `${arrets.length ? (faits / arrets.length) * 100 : 0}%` }} /></div>

        <ol className="points">
          {arrets.map((a) => {
            const final = FINAUX.includes(a.statut ?? "");
            const actif = courant?.order_id === a.order_id || ouvert === a.order_id;
            return (
              <li key={a.order_id} className={`point ${final ? "clos" : ""}`}>
                <div className="arret-tete">
                  <span className="num" style={{ fontWeight: 600 }}>{hhmm(a.arrivee_min)}</span>
                  <span style={{ flex: 1 }}><strong>{a.client || a.reference}</strong><br /><span className="muted">{a.adresse}</span></span>
                  <button className="link-btn" onClick={() => setOuvert(ouvert === a.order_id ? null : a.order_id)} aria-expanded={actif}>{actif ? "Réduire" : "Détails"}</button>
                </div>
                {a.statut && <p className="etat" style={{ color: a.statut === "impossible" ? "var(--rouge)" : a.statut === "livre" ? "var(--vert)" : undefined, fontWeight: 600 }}>
                  {a.statut === "arrive" ? "Sur place" : a.statut === "livre" ? "Livré" : `Impossible : ${t.motifs[a.motif ?? ""] ?? t.motifs[motif] ?? ""}`}</p>}
                {actif && (
                  <div className="arret-corps">
                    <p className="muted">Réf. {a.reference} · {a.palettes} pal. · {a.poids_kg} kg{a.fenetre_debut || a.fenetre_fin ? ` · fenêtre ${a.fenetre_debut ?? ""}-${a.fenetre_fin ?? ""}` : ""}</p>
                    {a.consignes && <p><strong>Consignes :</strong> {a.consignes}</p>}
                    {(a.contact_nom || a.contact_telephone) && <p><strong>Contact :</strong> {a.contact_nom} {a.contact_telephone && <a href={`tel:${a.contact_telephone.replace(/\s/g, "")}`}>{a.contact_telephone}</a>}</p>}
                    {a.lat !== null && !final && (
                      <a className="btn btn-xl" href={`https://www.google.com/maps/dir/?api=1&destination=${a.lat},${a.lng}&travelmode=driving`} target="_blank" rel="noreferrer">Naviguer</a>
                    )}
                    {!final && a.statut === null && <button className="btn btn-primary btn-xl" disabled={envoi} onClick={() => envoyer(a, "arrive")}>Je suis arrivé</button>}
                    {!final && mode === null && (
                      <div className="seg"><button className="ok" style={{ minHeight: 56 }} disabled={envoi} onClick={() => setMode("livre")}>Livré</button><button className="ko" style={{ minHeight: 56 }} disabled={envoi} onClick={() => setMode("impossible")}>Impossible</button></div>
                    )}
                    {!final && mode === "livre" && (
                      <div className="defaut-detail">
                        <div className="field"><label htmlFor="dest">Nom du destinataire (facultatif)</label><input id="dest" className="input" value={destinataire} onChange={(e) => setDestinataire(e.target.value)} maxLength={100} /></div>
                        <canvas ref={canvas} className="signature" width={800} height={340} aria-label="Signature du destinataire, à dessiner au doigt"
                          onPointerDown={(e) => { dessin.current = true; e.currentTarget.setPointerCapture(e.pointerId); const c = canvas.current!.getContext("2d")!; c.beginPath(); c.moveTo(...pt(e)); }}
                          onPointerMove={(e) => { if (!dessin.current) return; const c = canvas.current!.getContext("2d")!; c.lineWidth = 2.5; c.lineCap = "round"; c.strokeStyle = "#111418"; c.lineTo(...pt(e)); c.stroke(); setSigne(true); }}
                          onPointerUp={() => (dessin.current = false)} onPointerCancel={() => (dessin.current = false)} />
                        <label className="file-drop"><span>{photos.length ? `${photos.length} photo(s)` : "Photo de preuve (facultatif)"}</span>
                          <input type="file" accept="image/jpeg,image/png" capture="environment" onChange={(e) => { const f = e.target.files?.[0]; if (f) setPhotos([...photos, f].slice(0, 3)); e.target.value = ""; }} /></label>
                        <button className="btn btn-primary btn-xl" disabled={envoi} onClick={() => confirmer(a)}>Confirmer la livraison</button>
                        <button className="link-btn" onClick={() => setMode(null)}>Retour</button>
                      </div>
                    )}
                    {!final && mode === "impossible" && (
                      <div className="defaut-detail">
                        <div className="field"><label htmlFor="motif">Motif</label>
                          <select id="motif" className="select" style={{ minHeight: 52, fontSize: 17 }} value={motif} onChange={(e) => setMotif(e.target.value)}>{Object.entries(t.motifs).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
                        <div className="field"><label htmlFor="com">Précision (facultatif)</label><input id="com" className="input" value={commentaire} onChange={(e) => setCommentaire(e.target.value)} maxLength={300} /></div>
                        <label className="file-drop"><span>{photos.length ? `${photos.length} photo(s)` : "Photo (facultatif)"}</span>
                          <input type="file" accept="image/jpeg,image/png" capture="environment" onChange={(e) => { const f = e.target.files?.[0]; if (f) setPhotos([...photos, f].slice(0, 3)); e.target.value = ""; }} /></label>
                        <button className="btn btn-danger btn-xl" disabled={envoi} onClick={() => confirmer(a)}>Confirmer : livraison impossible</button>
                        <button className="link-btn" onClick={() => setMode(null)}>Retour</button>
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
        {arrets.length > 0 && !courant && <div className="result" role="status"><h1>Tournée terminée</h1><p>Tous les arrêts sont clôturés. Merci.</p></div>}
      </main>
    </>
  );
}
