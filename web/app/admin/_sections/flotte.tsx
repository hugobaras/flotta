"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Plaque } from "../../ui";

type Vehicule = {
  id: number; plaque: string; type: string; actif: boolean; hauteur_m: number | null; largeur_m: number | null; longueur_m: number | null;
  ptac_kg: number | null; charge_utile_kg: number | null; essieux: number | null; palettes: number | null; capacite_kg: number | null;
  capacite_m3: number | null; adr: boolean; frigo: boolean;
};
type Ligne = { ligne: number; plaque: string; erreurs: string[]; action: string | null };
type Apercu = { colonnes_ignorees: string[]; lignes: Ligne[]; total: number; valides: number; en_erreur: number };

const TYPES: Record<string, string> = { poids_lourd: "Poids lourd", porteur: "Porteur", semi_remorque: "Semi-remorque", utilitaire: "Utilitaire" };
const VIDE = { plaque: "", type: "poids_lourd", actif: true, hauteur_m: "", largeur_m: "", longueur_m: "", ptac_kg: "", charge_utile_kg: "", essieux: "", palettes: "", capacite_kg: "", capacite_m3: "", adr: false, frigo: false };
type Formulaire = typeof VIDE;

const NOMBRES = ["hauteur_m", "largeur_m", "longueur_m", "capacite_m3"] as const;
const ENTIERS = ["ptac_kg", "charge_utile_kg", "essieux", "palettes", "capacite_kg"] as const;
const LIBELLES: Record<string, string> = {
  hauteur_m: "Hauteur (m)", largeur_m: "Largeur (m)", longueur_m: "Longueur (m)", ptac_kg: "PTAC (kg)", charge_utile_kg: "Charge utile (kg)",
  essieux: "Essieux", palettes: "Palettes", capacite_kg: "Capacité (kg)", capacite_m3: "Volume (m³)",
};

export default function Flotte() {
  const [liste, setListe] = useState<Vehicule[] | null>(null);
  const [form, setForm] = useState<Formulaire>(VIDE);
  const [edition, setEdition] = useState<number | null>(null);
  const [erreur, setErreur] = useState("");
  const [fichier, setFichier] = useState<File | null>(null);
  const [apercu, setApercu] = useState<Apercu | null>(null);
  const [rapport, setRapport] = useState("");
  const dialogue = useRef<HTMLDialogElement>(null);
  const importDialogue = useRef<HTMLDialogElement>(null);

  const charger = useCallback(async () => {
    const r = await fetch("/api/admin/vehicules");
    if (r.status === 401) return (window.location.href = "/connexion");
    setListe(await r.json());
  }, []);

  useEffect(() => {
    charger();
  }, [charger]);

  function ouvrir(v?: Vehicule) {
    setEdition(v?.id ?? null);
    setForm(v ? ({ ...VIDE, ...Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x ?? ""])) } as Formulaire) : VIDE);
    setErreur("");
    dialogue.current?.showModal();
  }

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    const corps: Record<string, unknown> = { plaque: form.plaque, type: form.type, actif: form.actif, adr: form.adr, frigo: form.frigo };
    for (const c of NOMBRES) corps[c] = form[c] === "" ? "" : Number(String(form[c]).replace(",", "."));
    for (const c of ENTIERS) corps[c] = form[c] === "" ? "" : Number(form[c]);
    const r = await fetch(edition ? `/api/admin/vehicules/${edition}` : "/api/admin/vehicules", {
      method: edition ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      return setErreur(r.status === 409 ? "Cette plaque existe déjà." : Array.isArray(j.detail) ? j.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.at(-1)} : ${d.msg.replace("Value error, ", "")}`).join(" · ") : "Enregistrement impossible.");
    }
    dialogue.current?.close();
    charger();
  }

  async function supprimer(v: Vehicule) {
    if (!window.confirm(`Supprimer ${v.plaque} ?`)) return;
    const r = await fetch(`/api/admin/vehicules/${v.id}`, { method: "DELETE" });
    if (r.status === 409) window.alert("Ce véhicule a un historique de contrôles : désactivez-le plutôt que de le supprimer.");
    charger();
  }

  async function envoyerFichier(chemin: string) {
    const corps = new FormData();
    corps.append("fichier", fichier!);
    return fetch(chemin, { method: "POST", body: corps });
  }

  async function choisirFichier(f: File | null) {
    setFichier(f);
    setApercu(null);
    setRapport("");
    if (!f) return;
    const corps = new FormData();
    corps.append("fichier", f);
    const r = await fetch("/api/admin/vehicules/import/apercu", { method: "POST", body: corps });
    if (!r.ok) return setRapport((await r.json().catch(() => ({}))).detail ?? "Fichier illisible.");
    setApercu(await r.json());
  }

  async function importer() {
    const r = await envoyerFichier("/api/admin/vehicules/import");
    if (!r.ok) return setRapport("Import impossible.");
    const j = await r.json();
    setRapport(`${j.crees} véhicule(s) créé(s), ${j.mis_a_jour} mis à jour, ${j.ignores} ligne(s) ignorée(s).`);
    setApercu(null);
    setFichier(null);
    charger();
  }

  if (!liste) return <p className="muted">Chargement…</p>;
  const mm = (n: number | null) => (n === null ? "–" : String(n).replace(".", ","));

  return (
    <>
      <div className="page-head">
        <div>
          
          <p>Véhicules, gabarit et capacité. Le gabarit sert au calcul d'itinéraire poids lourd.</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <a className="btn" href="/api/admin/vehicules/qr.pdf">Imprimer les QR codes</a>
          <button className="btn" onClick={() => { setApercu(null); setFichier(null); setRapport(""); importDialogue.current?.showModal(); }}>Importer un fichier</button>
          <button className="btn btn-primary" onClick={() => ouvrir()}>Ajouter un véhicule</button>
        </div>
      </div>

      {liste.length === 0 ? (
        <div className="rack-empty"><strong>Aucun véhicule</strong>Ajoutez vos camions un par un ou importez un fichier CSV ou Excel.</div>
      ) : (
        <div className="table-wrap">
          <table className="rack rack-cards">
            <thead>
              <tr><th>Camion</th><th>Type</th><th>Gabarit H × l × L (m)</th><th>Capacité</th><th>Options</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {liste.map((v) => (
                <tr key={v.id} style={{ opacity: v.actif ? 1 : 0.55 }}>
                  <td><Plaque size="lg">{v.plaque}</Plaque></td>
                  <td>{TYPES[v.type] ?? v.type}{!v.actif && <span className="muted"> · inactif</span>}</td>
                  <td className="num">{mm(v.hauteur_m)} × {mm(v.largeur_m)} × {mm(v.longueur_m)}</td>
                  <td className="num">{v.palettes ?? "–"} pal. · {v.capacite_kg ?? "–"} kg</td>
                  <td>{[v.frigo && "Frigo", v.adr && "ADR"].filter(Boolean).join(", ") || <span className="muted">–</span>}</td>
                  <td className="right">
                    <button className="btn btn-ghost btn-sm" onClick={() => ouvrir(v)}>Modifier</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => supprimer(v)}>Supprimer</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <dialog ref={dialogue} className="dialog large" aria-labelledby="vh-titre">
        <form onSubmit={enregistrer}>
          <h2 id="vh-titre">{edition ? "Modifier le véhicule" : "Ajouter un véhicule"}</h2>
          <div className="form-grid">
            <div className="field"><label htmlFor="plaque">Plaque</label><input id="plaque" className="input" value={form.plaque} onChange={(e) => setForm({ ...form, plaque: e.target.value })} required autoFocus /></div>
            <div className="field"><label htmlFor="type">Type</label>
              <select id="type" className="select" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>{Object.entries(TYPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            </div>
            {[...NOMBRES, ...ENTIERS].map((c) => (
              <div className="field" key={c}><label htmlFor={c}>{LIBELLES[c]}</label>
                <input id={c} className="input" inputMode="decimal" value={String(form[c])} onChange={(e) => setForm({ ...form, [c]: e.target.value })} />
              </div>
            ))}
            <label className="check"><input type="checkbox" checked={form.frigo} onChange={(e) => setForm({ ...form, frigo: e.target.checked })} />Frigorifique</label>
            <label className="check"><input type="checkbox" checked={form.adr} onChange={(e) => setForm({ ...form, adr: e.target.checked })} />ADR (matières dangereuses)</label>
            <label className="check"><input type="checkbox" checked={form.actif} onChange={(e) => setForm({ ...form, actif: e.target.checked })} />En service</label>
          </div>
          {erreur && <div className="notice danger" role="alert" style={{ margin: 0 }}>{erreur}</div>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => dialogue.current?.close()}>Annuler</button>
            <button type="submit" className="btn btn-primary">Enregistrer</button>
          </div>
        </form>
      </dialog>

      <dialog ref={importDialogue} className="dialog large" aria-labelledby="imp-titre">
        <form onSubmit={(e) => { e.preventDefault(); importer(); }}>
          <div>
            <h2 id="imp-titre">Importer des véhicules</h2>
            <p className="muted" style={{ marginTop: 6 }}>Fichier CSV ou Excel avec une colonne « plaque ». Colonnes reconnues : type, hauteur, largeur, longueur, PTAC, charge utile, essieux, palettes, kg, m3, ADR, frigo.</p>
          </div>
          <input className="input" type="file" accept=".csv,.xlsx,text/csv" aria-label="Fichier à importer" onChange={(e) => choisirFichier(e.target.files?.[0] ?? null)} style={{ paddingTop: 6 }} />
          {rapport && <div className="notice" role="status" style={{ margin: 0 }}>{rapport}</div>}
          {apercu && (
            <>
              <p><strong>{apercu.valides}</strong> ligne(s) valide(s), <strong style={{ color: apercu.en_erreur ? "var(--rouge)" : undefined }}>{apercu.en_erreur}</strong> en erreur{apercu.colonnes_ignorees.length > 0 && <span className="muted"> · colonnes ignorées : {apercu.colonnes_ignorees.join(", ")}</span>}</p>
              <div className="scroll">
                <table className="rack">
                  <thead><tr><th>Ligne</th><th>Plaque</th><th>Résultat</th></tr></thead>
                  <tbody>
                    {apercu.lignes.map((l) => (
                      <tr key={l.ligne}>
                        <td className="num">{l.ligne}</td><td>{l.plaque}</td>
                        <td>{l.erreurs.length ? <span className="erreur">{l.erreurs.join(" · ")}</span> : l.action === "mettre_a_jour" ? "Mise à jour" : "Création"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => importDialogue.current?.close()}>Fermer</button>
            <button type="submit" className="btn btn-primary" disabled={!apercu || apercu.valides === 0}>Importer {apercu ? `${apercu.valides} véhicule(s)` : ""}</button>
          </div>
        </form>
      </dialog>
    </>
  );
}
