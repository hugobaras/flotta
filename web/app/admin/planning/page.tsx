"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Carte, { Point } from "../../lib/Carte";
import { Plaque } from "../../ui";

type Arret = { id: number; ordre: number; order_id: number; arrivee_min: number; depart_min: number; attente_min: number; reference: string; client: string; adresse: string; lat: number | null; lng: number | null };
type Tournee = { id: number; vehicle_id: number; plaque: string; depart_min: number; retour_min: number; distance_km: number; charge_kg: number; charge_palettes: number; arrets: Arret[] };
type NonAffectee = { order_id: number; reference?: string; adresse?: string; raison: string };
type Plan = {
  id: number; jour: string; statut: "en_attente" | "en_cours" | "termine" | "echec"; progression: number; message: string | null;
  resume: { km: number; duree_min: number; nb_tournees: number; nb_commandes: number; remplissage_pct: number | null; vehicules_exclus: { plaque: string; raison: string }[] } | null;
  routes: Tournee[]; non_affectees: NonAffectee[];
};

const COULEURS = ["#111418", "#e5560a", "#1a7f4b", "#2b6cb0", "#8a3ffc", "#c77700", "#d3281b", "#0f8b8d"];
const aujourdhui = () => new Date().toLocaleDateString("sv-SE");
const hhmm = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(Math.round(m % 60)).padStart(2, "0")}`;
const duree = (m: number) => `${Math.floor(m / 60)} h ${String(Math.round(m % 60)).padStart(2, "0")}`;
const json = { "Content-Type": "application/json" };

export default function Planning() {
  const [jour, setJour] = useState(aujourdhui);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [erreur, setErreur] = useState("");
  const [tempsMax, setTempsMax] = useState(10);
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
      const liste: { id: number; jour: string }[] = await r.json();
      const dernier = liste.find((p) => p.jour === jour);
      if (dernier) lire(dernier.id);
    })();
    return () => { if (minuteur.current) clearTimeout(minuteur.current); };
  }, [jour, lire]);

  async function optimiser() {
    setErreur("");
    const r = await fetch("/api/admin/plans", { method: "POST", headers: json, body: JSON.stringify({ jour, temps_max_s: tempsMax }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return setErreur(typeof j.detail === "string" ? j.detail : "Impossible de lancer le calcul.");
    setPlan({ id: j.id, jour, statut: "en_attente", progression: 0, message: null, resume: null, routes: [], non_affectees: [] });
    lire(j.id);
  }

  const points: Point[] = useMemo(
    () => (plan?.routes ?? []).flatMap((t, i) => t.arrets.filter((a) => a.lat !== null).map((a) => ({
      id: a.order_id, lat: a.lat!, lng: a.lng!, couleur: COULEURS[i % COULEURS.length], titre: `${t.plaque} · ${a.ordre}. ${a.reference}`,
    }))),
    [plan],
  );
  const enCours = plan && (plan.statut === "en_attente" || plan.statut === "en_cours");

  return (
    <>
      <div className="page-head">
        <div><h1>Planning</h1><p>Les tournées optimisées de la journée, par camion.</p></div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input className="input" type="date" aria-label="Jour à planifier" value={jour} onChange={(e) => setJour(e.target.value || aujourdhui())} />
          <label className="field" style={{ gridAutoFlow: "column", alignItems: "center", gap: 8 }}>
            <span className="hint">Calcul max.</span>
            <input className="input" type="number" min={1} max={120} value={tempsMax} onChange={(e) => setTempsMax(Number(e.target.value))} style={{ width: 80 }} aria-label="Temps de calcul maximal en secondes" />
            <span className="hint">s</span>
          </label>
          <button className="btn btn-primary" onClick={optimiser} disabled={!!enCours}>{enCours ? "Calcul en cours…" : plan ? "Recalculer" : "Optimiser"}</button>
        </div>
      </div>
      {erreur && <div className="notice danger" role="alert">{erreur}</div>}

      {enCours && (
        <div role="status" aria-live="polite">
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={plan.progression} aria-label="Avancement du calcul"><span style={{ width: `${plan.progression}%` }} /></div>
          <p className="muted">{plan.statut === "en_attente" ? "En attente de calcul…" : "Calcul des tournées…"} {plan.progression} %</p>
        </div>
      )}
      {plan?.statut === "echec" && <div className="notice danger" role="alert">{plan.message ?? "Le calcul a échoué."}</div>}

      {plan?.statut === "termine" && plan.resume && (
        <>
          <p style={{ fontSize: 18, marginBottom: 16 }}>
            <strong>{plan.resume.nb_tournees}</strong> tournée(s) · <strong>{plan.resume.km.toLocaleString("fr-FR")} km</strong> · {duree(plan.resume.duree_min)} de route et service
            {plan.resume.remplissage_pct !== null && <> · remplissage {plan.resume.remplissage_pct} %</>}
          </p>
          {plan.resume.vehicules_exclus.length > 0 && (
            <div className="notice" role="status">Camions non planifiés : {plan.resume.vehicules_exclus.map((e) => `${e.plaque} (${e.raison.toLowerCase()})`).join(", ")}</div>
          )}
          <div className="split">
            <div>
              {plan.routes.map((t, i) => (
                <section key={t.id} className="section" style={{ marginTop: i ? 32 : 0 }}>
                  <h2>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                      <span className="dot" style={{ background: COULEURS[i % COULEURS.length], width: 12, height: 12 }} aria-hidden /><Plaque>{t.plaque}</Plaque>
                    </span>
                    <small>{hhmm(t.depart_min)} → {hhmm(t.retour_min)} · {t.distance_km} km · {t.charge_kg} kg · {t.charge_palettes} pal.</small>
                  </h2>
                  <ol className="items">
                    {t.arrets.map((a) => (
                      <li key={a.id} className="item-row">
                        <span className="num" style={{ width: 52, fontWeight: 600 }}>{hhmm(a.arrivee_min)}</span>
                        <span className="item-label" style={{ fontWeight: 400 }}><strong>{a.reference}</strong> <span className="muted">· {a.client} · {a.adresse}{a.attente_min >= 1 ? ` · attente ${Math.round(a.attente_min)} min` : ""}</span></span>
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
              {plan.non_affectees.length > 0 && (
                <section className="section">
                  <h2>Non affectées <small>{plan.non_affectees.length}</small></h2>
                  <ul className="items">
                    {plan.non_affectees.map((n) => (
                      <li key={n.order_id} className="item-row" style={{ alignItems: "flex-start" }}>
                        <span className="item-label" style={{ fontWeight: 400 }}><strong>{n.reference ?? `#${n.order_id}`}</strong> <span className="muted">· {n.adresse}</span><br /><span style={{ color: "var(--rouge)" }}>{n.raison}</span></span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
            <div><Carte points={points} /></div>
          </div>
        </>
      )}
      {!plan && !erreur && <div className="rack-empty"><strong>Pas encore de plan pour ce jour</strong>Importez les commandes puis cliquez sur « Optimiser ».</div>}
    </>
  );
}
