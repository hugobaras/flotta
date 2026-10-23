"use client";

import { useCallback, useEffect, useState } from "react";
import { FlotteTabs } from "../../ui";

type Conducteur = { id: number; nom: string; actif: boolean; vehicule_habituel_id: number | null; vehicule_habituel: string | null };
type Vehicule = { id: number; plaque: string };

const json = { "Content-Type": "application/json" };

export default function Conducteurs() {
  const [liste, setListe] = useState<Conducteur[] | null>(null);
  const [vehicules, setVehicules] = useState<Vehicule[]>([]);
  const [nom, setNom] = useState("");
  const [habituel, setHabituel] = useState("");
  const [pin, setPin] = useState<{ nom: string; pin: string } | null>(null);
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    const r = await fetch("/api/admin/conducteurs");
    if (r.status === 401) return (window.location.href = "/connexion");
    setListe(await r.json());
    setVehicules(await (await fetch("/api/admin/vehicules")).json());
  }, []);

  useEffect(() => {
    charger();
  }, [charger]);

  async function creer(e: React.FormEvent) {
    e.preventDefault();
    setErreur("");
    const r = await fetch("/api/admin/conducteurs", { method: "POST", headers: json, body: JSON.stringify({ nom, vehicule_habituel_id: habituel ? Number(habituel) : null }) });
    if (!r.ok) return setErreur("Création impossible : le nom doit faire au moins 2 caractères.");
    const d = await r.json();
    setPin({ nom: d.nom, pin: d.pin });
    setNom("");
    setHabituel("");
    charger();
  }

  async function modifier(c: Conducteur, corps: object) {
    const r = await fetch(`/api/admin/conducteurs/${c.id}`, { method: "PATCH", headers: json, body: JSON.stringify(corps) });
    const d = await r.json();
    if (d.pin) setPin({ nom: c.nom, pin: d.pin });
    charger();
  }

  async function supprimer(c: Conducteur) {
    if (!window.confirm(`Supprimer ${c.nom} ?`)) return;
    const r = await fetch(`/api/admin/conducteurs/${c.id}`, { method: "DELETE" });
    if (r.status === 409) window.alert("Ce conducteur a des contrôles enregistrés : désactivez-le plutôt que de le supprimer.");
    charger();
  }

  if (!liste) return <p className="muted">Chargement…</p>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Flotte</h1>
          <p>Chaque conducteur a un code à 4 chiffres pour s'identifier sur son téléphone avant un contrôle.</p>
        </div>
      </div>
      <FlotteTabs actif="conducteurs" />

      {pin && (
        <div className="notice ok" role="status">
          <p>Code de <strong>{pin.nom}</strong> : <span className="pin-reveal">{pin.pin}</span></p>
          <p className="muted" style={{ marginTop: 4 }}>Notez-le maintenant : il ne sera plus affiché (il est conservé sous forme chiffrée).</p>
          <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => setPin(null)}>J'ai noté le code</button>
        </div>
      )}

      <form onSubmit={creer} className="toolbar">
        <input className="input" aria-label="Nom du conducteur" placeholder="Nom et prénom" value={nom} onChange={(e) => setNom(e.target.value)} required minLength={2} maxLength={100} />
        <select className="select" aria-label="Véhicule habituel" value={habituel} onChange={(e) => setHabituel(e.target.value)} style={{ width: "auto" }}>
          <option value="">Pas de véhicule habituel</option>
          {vehicules.map((v) => <option key={v.id} value={v.id}>{v.plaque}</option>)}
        </select>
        <button className="btn btn-primary" type="submit">Ajouter le conducteur</button>
      </form>
      {erreur && <div className="notice danger" role="alert">{erreur}</div>}

      {liste.length === 0 ? (
        <div className="rack-empty"><strong>Aucun conducteur</strong>Ajoutez vos conducteurs pour qu'ils s'identifient avec un code.</div>
      ) : (
        <div className="table-wrap">
          <table className="rack rack-cards">
            <thead><tr><th>Conducteur</th><th>Véhicule habituel</th><th>État</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {liste.map((c) => (
                <tr key={c.id} style={{ opacity: c.actif ? 1 : 0.55 }}>
                  <td style={{ fontWeight: 500 }}>{c.nom}</td>
                  <td>{c.vehicule_habituel ?? <span className="muted">–</span>}</td>
                  <td>{c.actif ? "Actif" : "Inactif"}</td>
                  <td className="right">
                    <button className="btn btn-ghost btn-sm" onClick={() => modifier(c, { reinitialiser_pin: true })}>Nouveau code</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => modifier(c, { actif: !c.actif })}>{c.actif ? "Désactiver" : "Réactiver"}</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => supprimer(c)}>Supprimer</button>
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
