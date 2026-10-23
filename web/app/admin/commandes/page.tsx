"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Carte, { Point } from "../../lib/Carte";

type Commande = {
  id: number; reference: string; client: string; adresse: string; lat: number | null; lng: number | null; geo_statut: string;
  poids_kg: number; palettes: number; fenetre_debut: string | null; fenetre_fin: string | null; frigo: boolean; adr: boolean; hayon: boolean;
};
type Champ = { cle: string; libelle: string; obligatoire: boolean };
type Ligne = { ligne: number; reference: string; erreurs: string[]; action: string | null };

const aujourdhui = () => new Date().toLocaleDateString("sv-SE");
const GEO: Record<string, { libelle: string; couleur: string }> = {
  ok: { libelle: "Localisée", couleur: "#1a7f4b" }, manuel: { libelle: "Placée à la main", couleur: "#1a7f4b" },
  douteux: { libelle: "À vérifier", couleur: "#c77700" }, introuvable: { libelle: "Introuvable", couleur: "#d3281b" },
  a_geocoder: { libelle: "En attente", couleur: "#9a9fa8" },
};
const json = { "Content-Type": "application/json" };

export default function Commandes() {
  const [jour, setJour] = useState(aujourdhui);
  const [liste, setListe] = useState<Commande[] | null>(null);
  const [filtre, setFiltre] = useState<"verifier" | "toutes">("toutes");
  const [selection, setSelection] = useState<number | null>(null);
  const [placement, setPlacement] = useState(false);
  const [message, setMessage] = useState("");
  const importDialogue = useRef<HTMLDialogElement>(null);
  // Assistant d'import
  const [fichier, setFichier] = useState<File | null>(null);
  const [colonnes, setColonnes] = useState<{ entetes: string[]; exemple: string[][]; champs: Champ[]; total: number } | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [dateDefaut, setDateDefaut] = useState(aujourdhui);
  const [memoriser, setMemoriser] = useState(true);
  const [apercu, setApercu] = useState<{ lignes: Ligne[]; valides: number; en_erreur: number } | null>(null);
  const [rapport, setRapport] = useState("");

  const charger = useCallback(async () => {
    const r = await fetch(`/api/admin/commandes?date=${jour}`);
    if (r.status === 401) return (window.location.href = "/connexion");
    setListe(await r.json());
  }, [jour]);

  useEffect(() => {
    charger();
  }, [charger]);

  const aVerifier = (c: Commande) => c.geo_statut !== "ok" && c.geo_statut !== "manuel";
  const visibles = useMemo(() => (liste ?? []).filter((c) => filtre === "toutes" || aVerifier(c)), [liste, filtre]);
  const points: Point[] = useMemo(
    () => visibles.filter((c) => c.lat !== null && c.lng !== null).map((c) => ({
      id: c.id, lat: c.lat!, lng: c.lng!, couleur: GEO[c.geo_statut]?.couleur ?? "#9a9fa8", titre: `${c.reference} · ${c.adresse}`, selectionne: c.id === selection,
    })),
    [visibles, selection],
  );

  async function placer(lat: number, lng: number) {
    if (!placement || selection === null) return;
    await fetch(`/api/admin/commandes/${selection}`, { method: "PATCH", headers: json, body: JSON.stringify({ lat, lng }) });
    setPlacement(false);
    charger();
  }

  async function relancer() {
    const r = await fetch(`/api/admin/commandes/geocoder?date=${jour}`, { method: "POST" });
    setMessage(r.status === 503 ? "Le service de géocodage est indisponible, réessayez plus tard." : "Géocodage relancé.");
    charger();
  }

  async function supprimer(c: Commande) {
    if (!window.confirm(`Supprimer la commande ${c.reference} ?`)) return;
    await fetch(`/api/admin/commandes/${c.id}`, { method: "DELETE" });
    setSelection(null);
    charger();
  }

  function ouvrirImport() {
    setFichier(null); setColonnes(null); setApercu(null); setRapport("");
    importDialogue.current?.showModal();
  }

  async function choisirFichier(f: File | null) {
    setFichier(f); setColonnes(null); setApercu(null); setRapport("");
    if (!f) return;
    const corps = new FormData();
    corps.append("fichier", f);
    const r = await fetch("/api/admin/commandes/import/colonnes", { method: "POST", body: corps });
    if (!r.ok) return setRapport((await r.json().catch(() => ({}))).detail ?? "Fichier illisible.");
    const j = await r.json();
    setColonnes(j);
    setMapping(j.mapping_propose);
  }

  const formulaire = (chemin: string) => {
    const corps = new FormData();
    corps.append("fichier", fichier!);
    corps.append("mapping", JSON.stringify(mapping));
    corps.append("date_defaut", dateDefaut);
    corps.append("memoriser", String(memoriser));
    return fetch(chemin, { method: "POST", body: corps });
  };

  async function voirApercu() {
    setRapport("");
    const r = await formulaire("/api/admin/commandes/import/apercu");
    if (!r.ok) return setRapport((await r.json().catch(() => ({}))).detail ?? "Aperçu impossible.");
    setApercu(await r.json());
  }

  async function importer() {
    const r = await formulaire("/api/admin/commandes/import");
    if (!r.ok) return setRapport((await r.json().catch(() => ({}))).detail ?? "Import impossible.");
    const j = await r.json();
    const g = j.geocodage;
    setRapport(`${j.crees} commande(s) créée(s), ${j.mis_a_jour} mise(s) à jour, ${j.ignores} ignorée(s). Adresses : ${g.ok} localisées, ${g.douteux} à vérifier, ${g.introuvable} introuvables${j.geocodage_indisponible ? ". Le service de géocodage est indisponible : relancez-le plus tard." : "."}`);
    setApercu(null); setFichier(null); setColonnes(null);
    charger();
  }

  if (!liste) return <p className="muted">Chargement…</p>;
  const nbVerifier = liste.filter(aVerifier).length;
  const attente = liste.filter((c) => c.geo_statut === "a_geocoder").length;
  const choisie = liste.find((c) => c.id === selection) ?? null;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Commandes</h1>
          <p>Les livraisons du jour et leur position sur la carte.</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input className="input" type="date" aria-label="Jour de livraison" value={jour} onChange={(e) => setJour(e.target.value || aujourdhui())} />
          {attente > 0 && <button className="btn" onClick={relancer}>Géocoder les {attente} en attente</button>}
          <button className="btn btn-primary" onClick={ouvrirImport}>Importer un fichier</button>
        </div>
      </div>
      {message && <div className="notice" role="status">{message}</div>}

      <div className="filtres" role="group" aria-label="Afficher">
        <button className="filtre" aria-pressed={filtre === "toutes"} onClick={() => setFiltre("toutes")}>Toutes <span className="count">{liste.length}</span></button>
        <button className="filtre" aria-pressed={filtre === "verifier"} onClick={() => setFiltre("verifier")}>Adresses à vérifier <span className="count">{nbVerifier}</span></button>
      </div>

      {liste.length === 0 ? (
        <div className="rack-empty"><strong>Aucune commande ce jour</strong>Importez un fichier CSV ou Excel pour commencer.</div>
      ) : (
        <div className="split">
          <div className="table-wrap">
            <table className="rack">
              <thead><tr><th>Commande</th><th>Adresse</th><th>Position</th></tr></thead>
              <tbody>
                {visibles.map((c) => (
                  <tr key={c.id} onClick={() => { setSelection(c.id); setPlacement(false); }} style={{ cursor: "pointer", background: c.id === selection ? "var(--white)" : undefined }}>
                    <td><strong>{c.reference}</strong><br /><span className="muted">{c.client}{c.palettes ? ` · ${c.palettes} pal.` : ""}{c.fenetre_debut ? ` · ${c.fenetre_debut}-${c.fenetre_fin ?? ""}` : ""}</span></td>
                    <td>{c.adresse}</td>
                    <td><span className="etat"><span className="dot" style={{ background: c.geo_statut === "a_geocoder" ? "transparent" : GEO[c.geo_statut]?.couleur, boxShadow: c.geo_statut === "a_geocoder" ? "inset 0 0 0 1.5px var(--gris)" : undefined }} />{GEO[c.geo_statut]?.libelle ?? c.geo_statut}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <Carte points={points} onPoint={(id) => { setSelection(id); setPlacement(false); }} onCarte={placer} curseur={placement} />
            {choisie && (
              <div className="selection">
                <p><strong>{choisie.reference}</strong> · {choisie.adresse}</p>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                  <button className={`btn btn-sm ${placement ? "btn-primary" : ""}`} onClick={() => setPlacement(!placement)}>{placement ? "Cliquez sur la carte…" : "Placer sur la carte"}</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => supprimer(choisie)}>Supprimer</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <dialog ref={importDialogue} className="dialog large" aria-labelledby="imp-titre">
        <form onSubmit={(e) => { e.preventDefault(); apercu ? importer() : voirApercu(); }}>
          <div>
            <h2 id="imp-titre">Importer des commandes</h2>
            <p className="muted" style={{ marginTop: 6 }}>Fichier CSV ou Excel. Vous associez ses colonnes aux champs de Flotta ; l'association est mémorisée.</p>
          </div>
          <input className="input" type="file" accept=".csv,.xlsx,text/csv" aria-label="Fichier à importer" onChange={(e) => choisirFichier(e.target.files?.[0] ?? null)} style={{ paddingTop: 6 }} />
          {rapport && <div className="notice" role="status" style={{ margin: 0 }}>{rapport}</div>}
          {colonnes && !apercu && (
            <>
              <p><strong>{colonnes.total}</strong> ligne(s) détectée(s). Associez les colonnes :</p>
              <div className="form-grid scroll">
                {colonnes.champs.map((c) => (
                  <div className="field" key={c.cle}>
                    <label htmlFor={`m-${c.cle}`}>{c.libelle}{c.obligatoire && " *"}</label>
                    <select id={`m-${c.cle}`} className="select" value={mapping[c.cle] ?? ""} onChange={(e) => setMapping({ ...mapping, [c.cle]: e.target.value })}>
                      <option value="">{c.obligatoire ? "Choisir une colonne" : "Non utilisé"}</option>
                      {colonnes.entetes.map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <div className="field" style={{ maxWidth: 240 }}>
                <label htmlFor="date-defaut">Date de livraison par défaut</label>
                <input id="date-defaut" className="input" type="date" value={dateDefaut} onChange={(e) => setDateDefaut(e.target.value)} />
                <span className="hint">Utilisée si le fichier n'a pas de colonne date ou si elle est vide.</span>
              </div>
              <label className="check"><input type="checkbox" checked={memoriser} onChange={(e) => setMemoriser(e.target.checked)} />Mémoriser cette association pour mes prochains imports</label>
            </>
          )}
          {apercu && (
            <>
              <p><strong>{apercu.valides}</strong> ligne(s) valide(s), <strong style={{ color: apercu.en_erreur ? "var(--rouge)" : undefined }}>{apercu.en_erreur}</strong> en erreur (ignorées à l'import).</p>
              <div className="scroll">
                <table className="rack">
                  <thead><tr><th>Ligne</th><th>Référence</th><th>Résultat</th></tr></thead>
                  <tbody>
                    {apercu.lignes.map((l) => (
                      <tr key={l.ligne}><td className="num">{l.ligne}</td><td>{l.reference}</td><td>{l.erreurs.length ? <span className="erreur">{l.erreurs.join(" · ")}</span> : l.action === "mettre_a_jour" ? "Mise à jour" : "Création"}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => importDialogue.current?.close()}>Fermer</button>
            {apercu && <button type="button" className="btn" onClick={() => setApercu(null)}>Modifier l'association</button>}
            <button type="submit" className="btn btn-primary" disabled={!colonnes || (apercu !== null && apercu.valides === 0)}>
              {apercu ? `Importer ${apercu.valides} commande(s)` : "Voir l'aperçu"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
