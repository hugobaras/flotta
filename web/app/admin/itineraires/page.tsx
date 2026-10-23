"use client";

import { useEffect, useMemo, useState } from "react";
import Carte, { Point } from "../../lib/Carte";
import { CommandesTabs, Plaque } from "../../ui";

type Vehicule = { id: number; plaque: string; actif: boolean; hauteur_m: number | null; largeur_m: number | null; longueur_m: number | null; ptac_kg: number | null };
type Depot = { id: number; nom: string; lat: number | null; lng: number | null; par_defaut: boolean };
type Commande = { id: number; reference: string; adresse: string; lat: number | null; lng: number | null };
type Resultat = {
  duree_s: number; distance_km: number; geometrie: { coordinates: [number, number][] }; avertissements: string[]; peage: boolean;
  estimation: { carburant_eur: number; peage_eur: number; cout_km_eur: number; total_eur: number };
};

const aujourdhui = () => new Date().toLocaleDateString("sv-SE");
const euros = (n: number) => n.toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
const duree = (s: number) => `${Math.floor(s / 3600)} h ${String(Math.round((s % 3600) / 60)).padStart(2, "0")} min`;

export default function Itineraires() {
  const [vehicules, setVehicules] = useState<Vehicule[]>([]);
  const [depots, setDepots] = useState<Depot[]>([]);
  const [commandes, setCommandes] = useState<Commande[]>([]);
  const [jour, setJour] = useState(aujourdhui);
  const [vehicule, setVehicule] = useState("");
  const [depot, setDepot] = useState("");
  const [arrets, setArrets] = useState<number[]>([]);
  const [retour, setRetour] = useState(true);
  const [dispo, setDispo] = useState<boolean | null>(null);
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const [erreur, setErreur] = useState("");
  const [calcul, setCalcul] = useState(false);

  useEffect(() => {
    (async () => {
      const v = await fetch("/api/admin/vehicules");
      if (v.status === 401) return (window.location.href = "/connexion");
      const liste: Vehicule[] = (await v.json()).filter((x: Vehicule) => x.actif);
      setVehicules(liste);
      setVehicule(String(liste[0]?.id ?? ""));
      const d: Depot[] = await (await fetch("/api/admin/depots")).json();
      setDepots(d);
      setDepot(String((d.find((x) => x.par_defaut) ?? d[0])?.id ?? ""));
      fetch("/api/admin/itineraires/etat").then(async (r) => setDispo((await r.json()).disponible)).catch(() => setDispo(false));
    })();
  }, []);

  useEffect(() => {
    fetch(`/api/admin/commandes?date=${jour}`).then(async (r) => r.ok && setCommandes((await r.json()).filter((c: Commande) => c.lat !== null)));
    setArrets([]);
  }, [jour]);

  const depotChoisi = depots.find((d) => String(d.id) === depot);
  const points: Point[] = useMemo(() => {
    const p: Point[] = commandes.filter((c) => arrets.includes(c.id)).map((c) => ({ id: c.id, lat: c.lat!, lng: c.lng!, couleur: "#111418", titre: `${arrets.indexOf(c.id) + 1}. ${c.reference}`, selectionne: false }));
    if (depotChoisi?.lat != null) p.push({ id: -1, lat: depotChoisi.lat!, lng: depotChoisi.lng!, couleur: "#e5560a", titre: "Dépôt", selectionne: true });
    return p;
  }, [commandes, arrets, depotChoisi]);

  function basculer(id: number) {
    setArrets((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));
    setResultat(null);
  }

  async function calculer() {
    setErreur(""); setResultat(null); setCalcul(true);
    const stops = arrets.map((id) => commandes.find((c) => c.id === id)!).map((c) => ({ lat: c.lat!, lng: c.lng! }));
    const base = depotChoisi?.lat != null ? [{ lat: depotChoisi.lat!, lng: depotChoisi.lng! }] : [];
    const pts = [...base, ...stops, ...(retour ? base : [])];
    try {
      const r = await fetch("/api/admin/itineraires", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vehicle_id: Number(vehicule), points: pts }) });
      const j = await r.json();
      if (!r.ok) setErreur(typeof j.detail === "string" ? j.detail : "Calcul impossible : vérifiez le véhicule et les arrêts.");
      else setResultat(j);
    } catch {
      setErreur("Le calcul a échoué. Vérifiez votre connexion.");
    }
    setCalcul(false);
  }

  const v = vehicules.find((x) => String(x.id) === vehicule);
  const gabaritIncomplet = v && (v.hauteur_m === null || v.largeur_m === null || v.longueur_m === null || v.ptac_kg === null);
  const nbPoints = arrets.length + (depotChoisi?.lat != null ? (retour ? 2 : 1) : 0);

  return (
    <>
      <div className="page-head">
        <div><h1>Commandes</h1><p>Itinéraire poids lourd adapté au gabarit du véhicule choisi.</p></div>
      </div>
      <CommandesTabs actif="itineraire" />

      {dispo === false && <div className="notice danger" role="alert">Le service de calcul d'itinéraire poids lourd est indisponible pour le moment. Aucun itinéraire ne peut être calculé.</div>}

      <div className="split">
        <div className="stack-form">
          <div className="form-grid">
            <div className="field"><label htmlFor="vh">Véhicule</label>
              <select id="vh" className="select" value={vehicule} onChange={(e) => { setVehicule(e.target.value); setResultat(null); }}>
                {vehicules.map((x) => <option key={x.id} value={x.id}>{x.plaque}</option>)}
              </select>
            </div>
            <div className="field"><label htmlFor="dp">Départ</label>
              <select id="dp" className="select" value={depot} onChange={(e) => { setDepot(e.target.value); setResultat(null); }}>
                {depots.map((x) => <option key={x.id} value={x.id}>{x.nom}</option>)}
              </select>
            </div>
            <div className="field"><label htmlFor="jr">Livraisons du</label><input id="jr" className="input" type="date" value={jour} onChange={(e) => setJour(e.target.value || aujourdhui())} /></div>
          </div>
          {gabaritIncomplet && <div className="notice danger" role="alert">Le gabarit de {v?.plaque} est incomplet : renseignez hauteur, largeur, longueur et PTAC dans la fiche du véhicule.</div>}

          <div>
            <p className="label" style={{ marginBottom: 8 }}>Arrêts, dans l'ordre de passage ({arrets.length})</p>
            {commandes.length === 0 ? <p className="muted">Aucune commande localisée ce jour-là.</p> : (
              <ul className="points" style={{ maxHeight: 280, overflow: "auto", border: "1px solid var(--line)", borderRadius: "var(--r)" }}>
                {commandes.map((c) => (
                  <li key={c.id} className="item-row" style={{ padding: "8px 12px" }}>
                    <label className="check" style={{ flex: 1 }}>
                      <input type="checkbox" checked={arrets.includes(c.id)} onChange={() => basculer(c.id)} />
                      <span>{arrets.includes(c.id) && <strong>{arrets.indexOf(c.id) + 1}. </strong>}{c.reference}<span className="muted"> · {c.adresse}</span></span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <label className="check"><input type="checkbox" checked={retour} onChange={(e) => { setRetour(e.target.checked); setResultat(null); }} />Retour au dépôt</label>
          <div><button className="btn btn-primary" onClick={calculer} disabled={calcul || !vehicule || nbPoints < 2 || dispo === false}>{calcul ? "Calcul en cours…" : "Calculer l'itinéraire"}</button></div>
          {erreur && <div className="notice danger" role="alert" style={{ margin: 0 }}>{erreur}</div>}

          {resultat && (
            <div className="resultat">
              <p style={{ fontSize: 22 }}><strong>{resultat.distance_km.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} km</strong> · {duree(resultat.duree_s)} {v && <Plaque>{v.plaque}</Plaque>}</p>
              {resultat.avertissements.map((w) => <div className="notice" key={w} role="status" style={{ margin: "8px 0 0" }}>{w}</div>)}
              <table className="rack" style={{ marginTop: 12 }}>
                <tbody>
                  <tr><td>Carburant (estimation)</td><td className="right num">{euros(resultat.estimation.carburant_eur)}</td></tr>
                  <tr><td>Péage (estimation){resultat.peage ? "" : " : aucun péage emprunté"}</td><td className="right num">{euros(resultat.estimation.peage_eur)}</td></tr>
                  <tr><td>Coût kilométrique</td><td className="right num">{euros(resultat.estimation.cout_km_eur)}</td></tr>
                  <tr><td><strong>Total estimé</strong></td><td className="right num"><strong>{euros(resultat.estimation.total_eur)}</strong></td></tr>
                </tbody>
              </table>
              <p className="hint" style={{ marginTop: 8 }}>Estimation indicative, calculée avec les hypothèses de vos Réglages.</p>
            </div>
          )}
        </div>
        <div>
          <Carte points={points} ligne={resultat?.geometrie.coordinates} />
        </div>
      </div>
    </>
  );
}
