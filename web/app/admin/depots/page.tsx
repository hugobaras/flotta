"use client";

import { useCallback, useEffect, useState } from "react";
import { FlotteTabs } from "../../ui";

type Depot = { id: number; nom: string; adresse: string; lat: number | null; lng: number | null; ouverture: string; fermeture: string; par_defaut: boolean };
const json = { "Content-Type": "application/json" };

export default function Depots() {
  const [liste, setListe] = useState<Depot[] | null>(null);
  const [form, setForm] = useState({ nom: "", adresse: "", ouverture: "06:00", fermeture: "19:00" });
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    const r = await fetch("/api/admin/depots");
    if (r.status === 401) return (window.location.href = "/connexion");
    setListe(await r.json());
  }, []);

  useEffect(() => {
    charger();
  }, [charger]);

  async function creer(e: React.FormEvent) {
    e.preventDefault();
    setErreur("");
    const r = await fetch("/api/admin/depots", { method: "POST", headers: json, body: JSON.stringify(form) });
    if (!r.ok) return setErreur("Création impossible : vérifiez le nom, l'adresse et les horaires.");
    setForm({ ...form, nom: "", adresse: "" });
    charger();
  }

  async function agir(d: Depot, corps: object) {
    await fetch(`/api/admin/depots/${d.id}`, { method: "PATCH", headers: json, body: JSON.stringify(corps) });
    charger();
  }

  async function supprimer(d: Depot) {
    if (!window.confirm(`Supprimer le dépôt ${d.nom} ?`)) return;
    const r = await fetch(`/api/admin/depots/${d.id}`, { method: "DELETE" });
    if (r.status === 409) window.alert("Une société doit garder au moins un dépôt.");
    charger();
  }

  if (!liste) return <p className="muted">Chargement…</p>;

  return (
    <>
      <div className="page-head">
        <div><h1>Flotte</h1><p>Les dépôts sont les points de départ et de retour des tournées.</p></div>
      </div>
      <FlotteTabs actif="depots" />

      <form onSubmit={creer} className="form-grid" style={{ marginBottom: 24 }}>
        <div className="field"><label htmlFor="d-nom">Nom</label><input id="d-nom" className="input" value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} required minLength={2} /></div>
        <div className="field wide"><label htmlFor="d-adr">Adresse</label><input id="d-adr" className="input" value={form.adresse} onChange={(e) => setForm({ ...form, adresse: e.target.value })} required minLength={3} /></div>
        <div className="field"><label htmlFor="d-ouv">Ouverture</label><input id="d-ouv" className="input" type="time" value={form.ouverture} onChange={(e) => setForm({ ...form, ouverture: e.target.value })} required /></div>
        <div className="field"><label htmlFor="d-fer">Fermeture</label><input id="d-fer" className="input" type="time" value={form.fermeture} onChange={(e) => setForm({ ...form, fermeture: e.target.value })} required /></div>
        <div style={{ alignSelf: "end" }}><button className="btn btn-primary" type="submit">Ajouter le dépôt</button></div>
      </form>
      {erreur && <div className="notice danger" role="alert">{erreur}</div>}

      {liste.length === 0 ? (
        <div className="rack-empty"><strong>Aucun dépôt</strong>Ajoutez au moins un dépôt avant de planifier des tournées.</div>
      ) : (
        <div className="table-wrap">
          <table className="rack rack-cards">
            <thead><tr><th>Dépôt</th><th>Adresse</th><th>Horaires</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {liste.map((d) => (
                <tr key={d.id}>
                  <td style={{ fontWeight: 500 }}>{d.nom}{d.par_defaut && <span className="muted"> · par défaut</span>}</td>
                  <td>{d.adresse}{d.lat === null && <span className="erreur"> · position inconnue</span>}</td>
                  <td className="num">{d.ouverture} - {d.fermeture}</td>
                  <td className="right">
                    {!d.par_defaut && <button className="btn btn-ghost btn-sm" onClick={() => agir(d, { par_defaut: true })}>Définir par défaut</button>}
                    <button className="btn btn-ghost btn-sm" onClick={() => supprimer(d)}>Supprimer</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
