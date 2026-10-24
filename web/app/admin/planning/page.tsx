"use client";

import { Panneau } from "../panneau";
import Commandes from "../_sections/commandes";
import Itineraires from "../_sections/itineraires";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Carte, { Point, Trace } from "../../lib/Carte";
import { Cadenas, Info, Plaque } from "../../ui";

type Arret = { id: number; ordre: number; rotation: number; order_id: number; arrivee_min: number; depart_min: number; attente_min: number; verrouille: boolean; reference: string; client: string; adresse: string; lat: number | null; lng: number | null; fenetre_fin: string | null; livraison: { statut: "arrive" | "livre" | "impossible" | null; arrive_le: string | null; termine_le: string | null; motif: string | null; nom_destinataire: string | null; a_signature: boolean; photos: number[] } | null; retard_min: number | null };
type Retard = { vehicle_id: number; plaque: string; order_id: number; reference: string; retard_min: number; message: string };
type Impact = { nb_retards: number; retard_total_min: number; km: number; retour_max_min: number; reportes: number };
type Proposition = { index: number; titre: string; description: string; actions: { order_id: number; vehicle_id: number | null; position: number | null }[]; impact: { avant: Impact; apres: Impact } };
type Lien = { vehicle_id: number; plaque: string; url: string; conducteur: string | null; email: string | null };
type Tournee = { id: number; vehicle_id: number; plaque: string; depart_min: number; retour_min: number; distance_km: number; charge_kg: number; charge_palettes: number; verrouille: boolean; arrets: Arret[]; conducteur_id: number | null; conduite_min: number; pauses: [number, number][]; plafond_conduite_min: number | null; conduite_restante_min: number | null; rotations: { numero: number; depart_min: number; retour_min: number; charge_palettes: number; charge_kg: number; nb_arrets: number }[] };
type ConducteurInfo = { id: number; nom: string; vehicle_id: number | null; conduite_jour_min: number; conduite_jour_normale_min: number; conduite_semaine_min: number; extensions_restantes: number; debut_possible_min: number };
type NonAffectee = { order_id: number; reference?: string; adresse?: string; raison: string };
type Indic = { km: number; duree_min: number; nb_tournees: number; nb_rotations?: number; remplissage_pct: number | null; nb_alertes: number; nb_non_affectees: number; nb_infractions?: number };
type Alerte = { type: string; message: string; route_vehicle_id: number; commande_id: number | null; gravite: "infraction" | "avertissement" };
type Plan = {
  id: number; jour: string; statut: "en_attente" | "en_cours" | "termine" | "echec"; progression: number; message: string | null; nom: string | null;
  resume: (Indic & { vehicules_exclus: { plaque: string; raison: string }[] }) | null; reference: Indic | null; routes: Tournee[]; non_affectees: NonAffectee[];
  parametres?: { rotations_max?: number }; alertes: Alerte[]; conducteurs: ConducteurInfo[]; publie_le: string | null; avancement: { total: number; livrees: number; impossibles: number; sur_place: number; en_retard: number } | null; peut_annuler: boolean; peut_retablir: boolean; versions: { id: number; nom: string | null; created_at: string; archive?: boolean; publie?: boolean }[];
};

const COULEURS = ["#111418", "#e5560a", "#1a7f4b", "#2b6cb0", "#8a3ffc", "#c77700", "#d3281b", "#0f8b8d"];
const aujourdhui = () => new Date().toLocaleDateString("sv-SE");
const hhmm = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(Math.round(m % 60)).padStart(2, "0")}`;
const duree = (m: number) => `${Math.floor(m / 60)} h ${String(Math.round(m % 60)).padStart(2, "0")}`;
const json = { "Content-Type": "application/json" };

function Delta({ valeur, ref, bas = true, unite = "" }: { valeur: number; ref: number | undefined; bas?: boolean; unite?: string }) {
  if (ref === undefined || valeur === ref) return null;
  const d = Math.round((valeur - ref) * 10) / 10;
  const mieux = bas ? d < 0 : d > 0;
  return <span className={`delta ${mieux ? "mieux" : "pire"}`}>{d > 0 ? "+" : "−"}{Math.abs(d).toLocaleString("fr-FR")}{unite}</span>;
}

export default function Planning() {
  const [jour, setJour] = useState(aujourdhui);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [erreur, setErreur] = useState("");
  const [tempsMax, setTempsMax] = useState(30);
  const [rotations, setRotations] = useState(true);  // plusieurs sorties du dépôt par camion
  const [rechargement, setRechargement] = useState(45);
  const [glisse, setGlisse] = useState<number | null>(null);
  const [sur, setSur] = useState<string | null>(null);
  const [pro, setPro] = useState(true);
  const [retardsPrevus, setRetardsPrevus] = useState<Retard[]>([]);
  const [trafic, setTrafic] = useState<{ actif: boolean; fournisseur: string | null; indisponible: boolean } | null>(null);
  const [propositions, setPropositions] = useState<{ demande: { type: string; order_id?: number; vehicle_id?: number }; titre: string; liste: Proposition[] } | null>(null);
  const [urgentes, setUrgentes] = useState<{ id: number; reference: string; adresse: string }[]>([]);
  const dialogueProp = useRef<HTMLDialogElement>(null);
  const [liens, setLiens] = useState<Lien[] | null>(null);
  const [copie, setCopie] = useState("");
  const dialogueLiens = useRef<HTMLDialogElement>(null);
  const minuteur = useRef<ReturnType<typeof setTimeout> | null>(null);

  const lire = useCallback(async (id: number) => {
    const r = await fetch(`/api/admin/plans/${id}`);
    if (r.status === 401) return (window.location.href = "/connexion");
    if (!r.ok) return;
    const p: Plan = await r.json();
    setPlan(p);
    if (p.statut === "en_attente" || p.statut === "en_cours") minuteur.current = setTimeout(() => lire(id), 1000);
  }, []);

  // Au changement de jour : on reprend le dernier plan de ce jour.
  useEffect(() => {
    setPlan(null);
    setErreur("");
    (async () => {
      const r = await fetch("/api/admin/plans");
      if (r.status === 401) return (window.location.href = "/connexion");
      const liste: { id: number; jour: string; archive: boolean; statut: string }[] = await r.json();
      const du_jour = liste.filter((p) => p.jour === jour);
      const dernier = du_jour.find((p) => !p.archive && p.statut !== "echec") ?? du_jour[0];  // le plus récent des calculs en cours, sinon un ancien
      if (dernier) lire(dernier.id);
    })();
    return () => { if (minuteur.current) clearTimeout(minuteur.current); };
  }, [jour, lire]);

  async function appeler(chemin: string, corps?: object) {
    setErreur("");
    const r = await fetch(`/api/admin/plans/${plan!.id}/${chemin}`, { method: "POST", headers: json, body: corps ? JSON.stringify(corps) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return setErreur(typeof j.detail === "string" ? j.detail : "Action impossible.");
    if (r.status === 202) lire(plan!.id);
    else setPlan(j);
  }

  async function publier() {
    setErreur("");
    const r = await fetch(`/api/admin/plans/${plan!.id}/publier`, { method: "POST" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return setErreur(typeof j.detail === "string" ? j.detail : "Publication impossible.");
    setLiens(j.liens);
    dialogueLiens.current?.showModal();
    lire(plan!.id);
  }

  useEffect(() => {
    fetch("/api/auth/me").then(async (r) => r.ok && setPro((await r.json()).fonctions.includes("temps_reel")));
  }, []);

  const chargerSuivi = useCallback(async (id: number) => {
    const r = await fetch(`/api/admin/plans/${id}/suivi`);
    if (!r.ok) return;
    const j = await r.json();
    setRetardsPrevus(j.retards);
    setTrafic(j.trafic);
  }, []);

  async function proposer(demande: { type: string; order_id?: number; vehicle_id?: number }, titre: string) {
    setErreur("");
    const r = await fetch(`/api/admin/plans/${plan!.id}/propositions`, { method: "POST", headers: json, body: JSON.stringify(demande) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return setErreur(typeof j.detail === "string" ? j.detail : "Impossible de calculer des propositions.");
    setPropositions({ demande, titre, liste: j.propositions });
    dialogueProp.current?.showModal();
  }

  async function appliquerProposition(p: Proposition) {
    const r = await fetch(`/api/admin/plans/${plan!.id}/propositions/appliquer`, { method: "POST", headers: json, body: JSON.stringify({ ...propositions!.demande, actions: p.actions }) });
    const j = await r.json().catch(() => ({}));
    dialogueProp.current?.close();
    if (!r.ok) return setErreur(typeof j.detail === "string" ? j.detail : "Application impossible.");
    setPlan(j);
    chargerSuivi(plan!.id);
  }

  async function ouvrirUrgence() {
    const r = await fetch(`/api/admin/commandes?date=${jour}`);
    if (r.ok) setUrgentes((await r.json()).filter((c: { statut: string; lat: number | null }) => c.statut === "a_planifier" && c.lat !== null));
    document.getElementById("urgence")?.scrollIntoView({ block: "center" });
  }

  async function copier(url: string) {
    try { await navigator.clipboard.writeText(url); setCopie(url); } catch { window.prompt("Copiez ce lien", url); }
  }

  // Tournées publiées : le suivi des livraisons se rafraîchit seul toutes les 30 secondes.
  useEffect(() => {
    if (!plan?.publie_le || plan.statut !== "termine") return;
    const id = plan.id;
    const t = setInterval(() => { lire(id); chargerSuivi(id); }, 30000);
    return () => clearInterval(t);
  }, [plan?.id, plan?.publie_le, plan?.statut, lire, chargerSuivi]);

  useEffect(() => {
    if (plan?.statut === "termine") chargerSuivi(plan.id);
  }, [plan?.id, plan?.statut, chargerSuivi]);

  async function optimiser() {
    setErreur("");
    const r = await fetch("/api/admin/plans", { method: "POST", headers: json, body: JSON.stringify({ jour, temps_max_s: tempsMax, rotations_max: rotations ? 3 : 1, rechargement_min: rechargement }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return setErreur(typeof j.detail === "string" ? j.detail : "Impossible de lancer le calcul.");
    setPlan({ id: j.id, jour, statut: "en_attente", progression: 0, message: null, nom: null, resume: null, reference: null, routes: [], non_affectees: [], alertes: [], conducteurs: [], publie_le: null, avancement: null, peut_annuler: false, peut_retablir: false, versions: [] });
    lire(j.id);
  }

  const deplacer = (order_id: number, vehicle_id: number | null, position?: number, rotation?: number) => appeler("deplacer", { order_id, vehicle_id, position, rotation });

  async function enregistrerVersion() {
    const nom = window.prompt("Nom de cette version du plan", "");
    if (nom?.trim()) {
      const r = await fetch(`/api/admin/plans/${plan!.id}/versions`, { method: "POST", headers: json, body: JSON.stringify({ nom }) });
      if (r.ok) setPlan(await r.json());
    }
  }

  const termine = plan?.statut === "termine";
  const utilisees = useMemo(() => (plan?.routes ?? []).filter((t) => t.arrets.length > 0 || t.verrouille), [plan]);
  const bornes = useMemo(() => {
    const t = (plan?.routes ?? []).filter((r) => r.arrets.length);
    if (!t.length) return { debut: 6 * 60, fin: 19 * 60 };
    return { debut: Math.floor(Math.min(...t.map((r) => r.depart_min)) / 60) * 60, fin: Math.ceil(Math.max(...t.map((r) => r.retour_min)) / 60) * 60 };
  }, [plan]);
  const couleurDe = (vid: number) => COULEURS[(plan?.routes ?? []).findIndex((t) => t.vehicle_id === vid) % COULEURS.length];
  const retards = new Set((plan?.alertes ?? []).filter((a) => a.type === "retard" && a.commande_id).map((a) => a.commande_id));
  const points: Point[] = useMemo(() => (plan?.routes ?? []).flatMap((t) => t.arrets.filter((a) => a.lat !== null).map((a) => ({ id: a.order_id, lat: a.lat!, lng: a.lng!, couleur: couleurDe(t.vehicle_id), titre: `${t.plaque} · ${a.ordre}. ${a.reference}` }))), // eslint-disable-next-line react-hooks/exhaustive-deps
    [plan]);
  const traces: Trace[] = useMemo(() => (plan?.routes ?? []).map((t) => ({ couleur: couleurDe(t.vehicle_id), coords: t.arrets.filter((a) => a.lat !== null).map((a) => [a.lng!, a.lat!] as [number, number]) })), // eslint-disable-next-line react-hooks/exhaustive-deps
    [plan]);
  const enCours = plan && (plan.statut === "en_attente" || plan.statut === "en_cours");
  const pos = (m: number) => `${((m - bornes.debut) / Math.max(1, bornes.fin - bornes.debut)) * 100}%`;
  const ref = plan?.reference ?? undefined;

  return (
    <>
      <div className="page-head">
        <div><h1>Planning</h1><p>Glissez un arrêt vers un autre camion : heures et alertes sont recalculées aussitôt.</p></div>
        <input className="input" type="date" aria-label="Jour à planifier" value={jour} onChange={(e) => setJour(e.target.value || aujourdhui())} />
      </div>

      <Panneau id="commandes" titre="Commandes du jour" defaut={!plan}><Commandes jour={jour} setJour={setJour} /></Panneau>

      <div className="barre-outils">
        <button className="btn btn-primary" onClick={optimiser} disabled={!!enCours}>{enCours ? "Calcul en cours…" : plan ? "Recalculer le plan" : "Optimiser"}</button>
        <label className="field" style={{ gridAutoFlow: "column", alignItems: "center", gap: 6 }}>
          <span className="hint">Calcul max.</span>
          <input className="input" type="number" min={1} max={120} value={tempsMax} onChange={(e) => setTempsMax(Number(e.target.value))} style={{ width: 72, minHeight: 34 }} aria-label="Temps de calcul maximal en secondes" />
          <span className="hint">s</span>
        </label>
        <label className="field" style={{ gridAutoFlow: "column", alignItems: "center", gap: 6 }}>
          <input type="checkbox" checked={rotations} onChange={(e) => setRotations(e.target.checked)} />
          <span className="hint">Plusieurs rotations par camion</span>
          {rotations && <><input className="input" type="number" min={15} max={240} value={rechargement} onChange={(e) => setRechargement(Number(e.target.value))} style={{ width: 72, minHeight: 34 }} aria-label="Temps de rechargement au dépôt en minutes" /><span className="hint">min de rechargement</span></>}
        </label>
        <Info>Un camion qui rentre au dépôt peut recharger et repartir (3 sorties au plus). Le chargement compte comme du travail, pas comme une pause du conducteur.</Info>
        {termine && (
          <>
            <button className="btn" onClick={() => appeler("reoptimiser")}>Réoptimiser (hors verrouillés)</button>
            <Info>Recalcule les tournées en gardant intactes celles que vous avez verrouillées avec le cadenas.</Info>
            <button className="btn btn-ghost" disabled={!plan!.peut_annuler} onClick={() => appeler("annuler")}>Annuler</button>
            <button className="btn btn-ghost" disabled={!plan!.peut_retablir} onClick={() => appeler("retablir")}>Rétablir</button>
            <button className="btn btn-ghost" onClick={enregistrerVersion}>Enregistrer une version</button>
            <button className="btn" onClick={publier}>{plan!.publie_le ? "Liens des chauffeurs" : "Publier aux chauffeurs"}</button>
            {plan!.versions.length > 1 && (
              <select className="select" style={{ width: "auto" }} aria-label="Version du plan" value={plan!.id} onChange={(e) => lire(Number(e.target.value))}>
                {[false, true].map((archive) => {
                  const liste = plan!.versions.filter((v) => !!v.archive === archive);
                  const options = liste.map((v) => <option key={v.id} value={v.id}>{v.nom ?? "Plan optimisé"}{v.publie ? " · publié" : ""} · {new Date(v.created_at).toLocaleTimeString("fr-FR", { timeStyle: "short" })}</option>);
                  return !liste.length ? null : archive ? <optgroup key="a" label="Anciens calculs">{options}</optgroup> : options;
                })}
              </select>
            )}
          </>
        )}
      </div>
      {erreur && <div className="notice danger" role="alert">{erreur}</div>}

      {enCours && (
        <div role="status" aria-live="polite">
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={plan.progression} aria-label="Avancement du calcul"><span style={{ width: `${plan.progression}%` }} /></div>
          <p className="muted">{plan.statut === "en_attente" ? "En attente de calcul…" : "Calcul des tournées…"} {plan.progression} %</p>
        </div>
      )}
      {plan?.statut === "echec" && <div className="notice danger" role="alert">{plan.message ?? "Le calcul a échoué."}</div>}
      {termine && plan!.message && <div className="notice" role="status">{plan!.message}</div>}

      {termine && plan!.resume && (
        <>
          <dl className="indicateurs" aria-label="Indicateurs du plan, comparés au plan initial">
            <div><dt>Distance</dt><dd>{plan!.resume.km.toLocaleString("fr-FR")} km<Delta valeur={plan!.resume.km} ref={ref?.km} unite=" km" /></dd></div>
            <div><dt>Durée totale</dt><dd>{duree(plan!.resume.duree_min)}<Delta valeur={plan!.resume.duree_min} ref={ref?.duree_min} unite=" min" /></dd></div>
            {(plan!.resume.nb_rotations ?? 0) > plan!.resume.nb_tournees && <div><dt>Rotations</dt><dd>{plan!.resume.nb_rotations}<span className="muted"> sur {plan!.resume.nb_tournees} camions</span></dd></div>}
            <div><dt>Remplissage</dt><dd>{plan!.resume.remplissage_pct ?? "–"}{plan!.resume.remplissage_pct !== null && " %"}{plan!.resume.remplissage_pct !== null && <Delta valeur={plan!.resume.remplissage_pct} ref={ref?.remplissage_pct ?? undefined} bas={false} unite=" pt" />}</dd></div>
            <div><dt>Alertes</dt><dd>{plan!.resume.nb_alertes}<Delta valeur={plan!.resume.nb_alertes} ref={ref?.nb_alertes} /></dd></div>
            <div><dt>Non affectées</dt><dd>{plan!.resume.nb_non_affectees}<Delta valeur={plan!.resume.nb_non_affectees} ref={ref?.nb_non_affectees} /></dd></div>
          </dl>
          {plan!.resume.vehicules_exclus.length > 0 && <div className="notice" role="status">Camions non planifiés : {plan!.resume.vehicules_exclus.map((e) => `${e.plaque} (${e.raison.toLowerCase()})`).join(", ")}</div>}
          {trafic && <p className="hint" style={{ marginBottom: 8 }}>Trafic en direct : {!trafic.actif ? "désactivé (durées du plan)" : trafic.indisponible ? `${trafic.fournisseur} indisponible, durées du plan` : `actif (${trafic.fournisseur})`}.</p>}
          {retardsPrevus.length > 0 && (
            <div className="notice danger" role="alert" aria-label="Retards prévus">
              <strong>{retardsPrevus.length} retard{retardsPrevus.length > 1 ? "s" : ""} prévu{retardsPrevus.length > 1 ? "s" : ""} sur une fenêtre horaire</strong>
              <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                {retardsPrevus.map((r) => <li key={r.order_id}>{r.message} <button className="link-btn" style={{ minHeight: 0, padding: 0 }} onClick={() => proposer({ type: "retard" }, `Retard sur ${r.reference}`)}>Voir des solutions</button></li>)}
              </ul>
            </div>
          )}
          {!pro && <p className="hint" style={{ marginBottom: 8 }}>Suivi des retards, commande urgente et panne : fonctions de l'offre Pro.</p>}
          {pro && <div id="urgence" className="barre-outils">
            <button className="btn btn-sm" onClick={ouvrirUrgence}>Commande urgente…</button>
            {urgentes.length > 0 && (
              <select className="select" style={{ width: "auto" }} aria-label="Commande urgente à insérer" value="" onChange={(e) => e.target.value && proposer({ type: "urgence", order_id: Number(e.target.value) }, "Commande urgente")}>
                <option value="">Choisir la commande…</option>
                {urgentes.map((c) => <option key={c.id} value={c.id}>{c.reference} · {c.adresse}</option>)}
              </select>
            )}
          </div>}
          {plan!.avancement && (
            <div className="notice ok" role="status">
              <strong>Suivi en direct :</strong> {plan!.avancement.livrees} livrée{plan!.avancement.livrees > 1 ? "s" : ""} sur {plan!.avancement.total}
              {plan!.avancement.sur_place > 0 && <> · {plan!.avancement.sur_place} sur place</>}
              {plan!.avancement.impossibles > 0 && <> · <strong style={{ color: "var(--rouge)" }}>{plan!.avancement.impossibles} impossible{plan!.avancement.impossibles > 1 ? "s" : ""}</strong></>}
              {plan!.avancement.en_retard > 0 && <> · <strong style={{ color: "var(--rouge)" }}>{plan!.avancement.en_retard} en retard</strong></>}
            </div>
          )}
          {plan!.alertes.length > 0 && <ul className="alertes" role="alert" aria-label="Alertes du plan">{plan!.alertes.map((a, i) => <li key={i} className={a.gravite === "infraction" ? "infraction" : ""}>{a.gravite === "infraction" && <strong>Infraction · </strong>}{a.message}</li>)}</ul>}

          {plan!.conducteurs.length > 0 && (
            <details className="restants">
              <summary>Temps de conduite restants des conducteurs</summary>
              <table className="rack">
                <thead><tr><th>Conducteur</th><th>Aujourd'hui</th><th>Semaine</th><th>Extensions à 10 h</th><th>Départ possible</th></tr></thead>
                <tbody>
                  {plan!.conducteurs.map((c) => (
                    <tr key={c.id}><td>{c.nom}</td><td className="num">{duree(c.conduite_jour_normale_min)}{c.conduite_jour_min > c.conduite_jour_normale_min && ` (jusqu'à ${duree(c.conduite_jour_min)})`}</td><td className="num">{duree(c.conduite_semaine_min)}</td><td className="num">{c.extensions_restantes}</td><td className="num">{hhmm(c.debut_possible_min)}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="hint" style={{ marginTop: 6 }}>Calculés à partir des activités déclarées (page Flotte, onglet Conducteurs). Sans historique, un conducteur est supposé reposé.</p>
            </details>
          )}

          <div className="split">
            <div>
              {utilisees.map((t, i) => (
                <section key={t.vehicle_id} className="section" style={{ marginTop: i ? 32 : 0 }}
                  onDragOver={(e) => { if (glisse !== null && !t.verrouille) { e.preventDefault(); setSur(`r${t.vehicle_id}`); } }}
                  onDragLeave={() => setSur(null)}
                  onDrop={(e) => { e.preventDefault(); setSur(null); if (glisse !== null) deplacer(glisse, t.vehicle_id); setGlisse(null); }}>
                  <h2>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                      <span className="dot" style={{ background: couleurDe(t.vehicle_id), width: 12, height: 12 }} aria-hidden /><Plaque>{t.plaque}</Plaque>
                      <button className="btn btn-ghost btn-sm" aria-pressed={t.verrouille} onClick={() => appeler("verrouiller", { vehicle_id: t.vehicle_id, verrouille: !t.verrouille })}><Cadenas ferme={t.verrouille} />{t.verrouille ? "Tournée verrouillée" : "Verrouiller"}</button>
                      {pro && !t.verrouille && t.arrets.length > 0 && <button className="btn btn-ghost btn-sm" onClick={() => proposer({ type: "panne", vehicle_id: t.vehicle_id }, `Panne de ${t.plaque}`)}>Panne…</button>}
                    </span>
                    <small>{t.arrets.length ? `${hhmm(t.depart_min)} → ${hhmm(t.retour_min)} · ${t.distance_km} km · ${t.charge_kg} kg · ${t.charge_palettes} pal.` : "Aucun arrêt"}</small>
                  </h2>
                  <div className="conducteur-ligne">
                    <label className="hint" htmlFor={`cd-${t.vehicle_id}`}>Conducteur</label>
                    <select id={`cd-${t.vehicle_id}`} className="select" disabled={t.verrouille} value={t.conducteur_id ?? ""}
                      onChange={(e) => appeler("affecter", { vehicle_id: t.vehicle_id, conducteur_id: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">Sans conducteur (règles par tournée)</option>
                      {plan!.conducteurs.map((c) => <option key={c.id} value={c.id} disabled={c.vehicle_id !== null && c.vehicle_id !== t.vehicle_id}>{c.nom}</option>)}
                    </select>
                    {t.arrets.length > 0 && t.plafond_conduite_min !== null && (
                      <span className={t.conduite_restante_min !== null && t.conduite_restante_min < 0 ? "delta pire" : "muted"}>
                        Conduite {duree(t.conduite_min)} sur {duree(t.plafond_conduite_min)} · {t.pauses.length} pause{t.pauses.length > 1 ? "s" : ""} de 45 min
                      </span>
                    )}
                  </div>
                  {t.arrets.length > 0 && (
                    <>
                      <div className="frise" role="img" aria-label={`Frise horaire de ${t.plaque}`}>
                        {t.rotations.slice(1).map((r, k) => <span key={`d${r.numero}`} className="bloc depot" title={`Rechargement ${hhmm(t.rotations[k].retour_min)}-${hhmm(r.depart_min)}`} style={{ left: pos(t.rotations[k].retour_min), width: `max(4px, calc(${pos(r.depart_min)} - ${pos(t.rotations[k].retour_min)}))` }} />)}
                        {t.pauses.map(([d, f]) => <span key={d} className="bloc pause" title={`Pause ${hhmm(d)}-${hhmm(f)}`} style={{ left: pos(d), width: `max(4px, calc(${pos(f)} - ${pos(d)}))` }} />)}
                        {t.arrets.map((a) => (
                          <span key={a.id}>
                            {a.attente_min >= 1 && <span className="attente" style={{ left: pos(a.arrivee_min - a.attente_min), width: `calc(${pos(a.arrivee_min)} - ${pos(a.arrivee_min - a.attente_min)})` }} />}
                            <span className={`bloc ${retards.has(a.order_id) ? "retard" : ""}`} title={`${a.reference} ${hhmm(a.arrivee_min)}-${hhmm(a.depart_min)}`}
                              style={{ left: pos(a.arrivee_min), width: `max(4px, calc(${pos(a.depart_min)} - ${pos(a.arrivee_min)}))`, background: couleurDe(t.vehicle_id) }} />
                          </span>
                        ))}
                      </div>
                      <div className="frise-axe" aria-hidden><span>{hhmm(bornes.debut)}</span><span>{hhmm(bornes.fin)}</span></div>
                    </>
                  )}
                  <ol className="items" style={{ borderBottom: 0 }}>
                    {t.arrets.map((a, n) => (
                      <Fragment key={a.id}>
                      {t.pauses.filter(([, f]) => f <= a.arrivee_min && (n === 0 || f > t.arrets[n - 1].arrivee_min)).map(([d, f]) => (
                        <li key={`p${d}`} className="pause-ligne"><span className="heure">{hhmm(d)}</span><span className="corps">Pause obligatoire de {Math.round(f - d)} min <span className="muted">(4 h 30 de conduite, règlement CE 561/2006)</span></span></li>
                      ))}
                      {t.rotations.length > 1 && (n === 0 || a.rotation !== t.arrets[n - 1].rotation) && (() => {
                        const r = t.rotations.find((x) => x.numero === a.rotation);
                        return r ? (
                          <li key={`rot${a.rotation}`} className="rotation-ligne">
                            <span className="heure">{hhmm(r.depart_min)}</span>
                            <span className="corps"><strong>Rotation {r.numero}</strong> <span className="muted">· {n > 0 ? `retour au dépôt à ${hhmm(t.rotations[a.rotation - 2].retour_min)}, rechargement, ` : ""}départ {hhmm(r.depart_min)}, retour {hhmm(r.retour_min)} · {r.charge_palettes} pal. · {r.nb_arrets} arrêt{r.nb_arrets > 1 ? "s" : ""}</span></span>
                          </li>
                        ) : null;
                      })()}
                      <li
                        className={`stop ${a.verrouille || t.verrouille ? "verrou" : ""} ${sur === `s${a.order_id}` ? "sur" : ""}`}
                        draggable={!a.verrouille && !t.verrouille}
                        onDragStart={() => setGlisse(a.order_id)}
                        onDragEnd={() => { setGlisse(null); setSur(null); }}
                        onDragOver={(e) => { if (glisse !== null && glisse !== a.order_id && !t.verrouille) { e.preventDefault(); e.stopPropagation(); setSur(`s${a.order_id}`); } }}
                        onDrop={(e) => { e.preventDefault(); e.stopPropagation(); setSur(null); if (glisse !== null && glisse !== a.order_id) deplacer(glisse, t.vehicle_id, n); setGlisse(null); }}>
                        <span className="heure" style={{ color: retards.has(a.order_id) ? "var(--rouge)" : undefined }}>{hhmm(a.arrivee_min)}</span>
                        <span className="corps"><strong>{a.reference}</strong> <span className="muted">· {a.client} · {a.adresse}{a.fenetre_fin ? ` · avant ${a.fenetre_fin}` : ""}{a.attente_min >= 1 ? ` · attente ${Math.round(a.attente_min)} min` : ""}</span>
                          {a.livraison?.statut && <><br /><span style={{ fontWeight: 600, color: a.livraison.statut === "impossible" ? "var(--rouge)" : a.livraison.statut === "livre" ? "var(--vert)" : undefined }}>
                            {a.livraison.statut === "arrive" ? `Sur place depuis ${new Date(a.livraison.arrive_le!).toLocaleTimeString("fr-FR", { timeStyle: "short" })}` : a.livraison.statut === "livre" ? `Livré à ${new Date(a.livraison.termine_le!).toLocaleTimeString("fr-FR", { timeStyle: "short" })}${a.livraison.nom_destinataire ? ` · ${a.livraison.nom_destinataire}` : ""}` : `Impossible à ${new Date(a.livraison.termine_le!).toLocaleTimeString("fr-FR", { timeStyle: "short" })} · ${a.livraison.motif}`}</span>
                            {a.livraison.a_signature && a.livraison.termine_le && <> · signature</>}{a.livraison.photos.length > 0 && <> · {a.livraison.photos.map((p) => <a key={p} href={`/api/admin/plans/livraisons/photos/${p}`} target="_blank" rel="noreferrer">photo</a>).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, ", ", el] : [el]), [])}</>}</>}
                          {a.retard_min ? <><br /><span style={{ color: "var(--rouge)", fontWeight: 600 }}>En retard de {a.retard_min} min</span></> : null}</span>
                        <select className="select" aria-label={`Déplacer ${a.reference} vers`} value="" disabled={a.verrouille || t.verrouille}
                          onChange={(e) => { const v = e.target.value; if (!v) return; if (v.startsWith("rot:")) deplacer(a.order_id, t.vehicle_id, undefined, Number(v.slice(4))); else deplacer(a.order_id, v === "aucun" ? null : Number(v)); }}>
                          <option value="">Déplacer…</option>
                          {t.rotations.filter((r) => r.numero !== a.rotation).map((r) => <option key={`r${r.numero}`} value={`rot:${r.numero}`}>Rotation {r.numero} de ce camion</option>)}
                          {t.rotations.length < (plan!.parametres?.rotations_max ?? 3) && t.rotations.length > 0 && !(t.rotations.length === 1 && t.arrets.length === 1) && <option value={`rot:${t.rotations.length + 1}`}>Nouvelle rotation de ce camion</option>}
                          {plan!.routes.filter((r) => r.vehicle_id !== t.vehicle_id && !r.verrouille).map((r) => <option key={r.vehicle_id} value={r.vehicle_id}>{r.plaque}</option>)}
                          <option value="aucun">Retirer du plan</option>
                        </select>
                        <button className="btn btn-ghost btn-icon" aria-pressed={a.verrouille} aria-label={`${a.verrouille ? "Déverrouiller" : "Verrouiller"} ${a.reference}`} disabled={t.verrouille}
                          onClick={() => appeler("verrouiller", { order_id: a.order_id, verrouille: !a.verrouille })}><Cadenas ferme={a.verrouille} /></button>
                      </li>
                      </Fragment>
                    ))}
                    {t.pauses.filter(([d]) => t.arrets.length > 0 && d >= t.arrets[t.arrets.length - 1].depart_min).map(([d, f]) => (
                      <li key={`pf${d}`} className="pause-ligne"><span className="heure">{hhmm(d)}</span><span className="corps">Pause obligatoire de {Math.round(f - d)} min sur le retour</span></li>
                    ))}
                  </ol>
                </section>
              ))}

              <section className="section" aria-labelledby="non-aff" onDragOver={(e) => { if (glisse !== null) { e.preventDefault(); setSur("non"); } }} onDragLeave={() => setSur(null)}
                onDrop={(e) => { e.preventDefault(); setSur(null); if (glisse !== null) deplacer(glisse, null); setGlisse(null); }}>
                <h2 id="non-aff">Non affectées <small>{plan!.non_affectees.length}</small></h2>
                <div className={`zone-depot ${sur === "non" ? "sur" : ""}`}>Déposez ici un arrêt pour le retirer du plan.</div>
                <ul className="items" style={{ borderBottom: 0 }}>
                  {plan!.non_affectees.map((n) => (
                    <li key={n.order_id} className="stop" draggable onDragStart={() => setGlisse(n.order_id)} onDragEnd={() => { setGlisse(null); setSur(null); }} style={{ alignItems: "flex-start" }}>
                      <span className="corps"><strong>{n.reference ?? `#${n.order_id}`}</strong> <span className="muted">· {n.adresse}</span><br /><span style={{ color: "var(--rouge)" }}>{n.raison}</span></span>
                      <select className="select" aria-label={`Affecter ${n.reference ?? n.order_id} à`} value="" onChange={(e) => e.target.value && deplacer(n.order_id, Number(e.target.value))}>
                        <option value="">Affecter à…</option>
                        {plan!.routes.filter((r) => !r.verrouille).map((r) => <option key={r.vehicle_id} value={r.vehicle_id}>{r.plaque}</option>)}
                      </select>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
            <div>
              <Carte points={points} traces={traces} />
              <p className="hint" style={{ marginTop: 6 }}>Les tracés pointillés montrent l'ordre de passage à vol d'oiseau, pas l'itinéraire routier.</p>
            </div>
          </div>
        </>
      )}
      <dialog ref={dialogueProp} className="dialog large" aria-labelledby="prop-titre">
        <div style={{ display: "grid", gap: 18, padding: 24 }}>
          <div>
            <h2 id="prop-titre">{propositions?.titre}</h2>
            <p className="muted" style={{ marginTop: 6 }}>Rien n'est modifié tant que vous n'appliquez pas une solution. Chaque solution est annulable.</p>
          </div>
          {propositions && propositions.liste.length === 0 && <div className="notice" role="status" style={{ margin: 0 }}>Aucune solution n'améliore la situation avec les camions disponibles.</div>}
          {propositions?.liste.map((p) => (
            <div key={p.index} className="solution">
              <div style={{ flex: 1 }}>
                <strong>{p.titre}</strong>
                <p className="muted">{p.description}</p>
                <p className="num" style={{ fontSize: 14 }}>
                  Retards {p.impact.avant.nb_retards} → {p.impact.apres.nb_retards} · retour au plus tard {hhmm(p.impact.apres.retour_max_min)} · {p.impact.apres.km.toLocaleString("fr-FR")} km restants
                  {p.impact.apres.reportes > 0 && ` · ${p.impact.apres.reportes} arrêt(s) reporté(s)`}
                </p>
              </div>
              <button className="btn btn-primary btn-sm" onClick={() => appliquerProposition(p)}>Appliquer</button>
            </div>
          ))}
          <div className="dialog-actions"><button className="btn" onClick={() => dialogueProp.current?.close()}>Fermer</button></div>
        </div>
      </dialog>
      <dialog ref={dialogueLiens} className="dialog large" aria-labelledby="liens-titre">
        <div style={{ display: "grid", gap: 18, padding: 24 }}>
          <div>
            <h2 id="liens-titre">Liens des chauffeurs</h2>
            <p className="muted" style={{ marginTop: 6 }}>Chaque chauffeur ouvre son lien sur son téléphone. La tournée ne s'affiche qu'une fois le contrôle avant départ du camion fait. Le lien est aussi accessible depuis le QR code du camion.</p>
          </div>
          <table className="rack">
            <thead><tr><th>Camion</th><th>Conducteur</th><th>Lien</th></tr></thead>
            <tbody>
              {(liens ?? []).map((l) => (
                <tr key={l.vehicle_id}>
                  <td><Plaque>{l.plaque}</Plaque></td>
                  <td>{l.conducteur ?? <span className="muted">Non affecté</span>}{l.email && <span className="muted"> · envoyé à {l.email}</span>}</td>
                  <td><button className="btn btn-sm" onClick={() => copier(l.url)}>{copie === l.url ? "Copié" : "Copier le lien"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">Les emails ne partent que si Brevo est configuré et si le conducteur a une adresse. Republier après une modification met à jour les tournées sans changer les liens.</p>
          <div className="dialog-actions"><button className="btn" onClick={() => dialogueLiens.current?.close()}>Fermer</button></div>
        </div>
      </dialog>
      {!plan && !erreur && <div className="rack-empty"><strong>Pas encore de plan pour ce jour</strong>Importez les commandes puis cliquez sur « Optimiser ».</div>}
      <Panneau id="itineraire" titre="Calculer un itinéraire poids lourd"><Itineraires /></Panneau>
    </>
  );
}
