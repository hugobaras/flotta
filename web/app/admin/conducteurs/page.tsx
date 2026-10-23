"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FlotteTabs } from "../../ui";

type Conducteur = { id: number; nom: string; actif: boolean; vehicule_habituel_id: number | null; vehicule_habituel: string | null };
type Vehicule = { id: number; plaque: string };

type Activite = { id: number; type: string; debut: string; fin: string };
type Compteurs = {
  conduite_continue_min: number; conduite_jour_min: number; conduite_jour_normale_min: number; extensions_restantes: number; conduite_semaine_min: number;
  debut_possible: string; infractions: { code: string; message: string; debut: string }[]; notes: string[];
};
const TYPES: Record<string, string> = { conduite: "Conduite", travail: "Autre tâche", disponibilite: "Disponibilité", repos: "Repos ou pause" };
const duree = (m: number) => `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
const quand = (iso: string) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
const json = { "Content-Type": "application/json" };

export default function Conducteurs() {
  const [liste, setListe] = useState<Conducteur[] | null>(null);
  const [vehicules, setVehicules] = useState<Vehicule[]>([]);
  const [nom, setNom] = useState("");
  const [habituel, setHabituel] = useState("");
  const [pin, setPin] = useState<{ nom: string; pin: string } | null>(null);
  const [erreur, setErreur] = useState("");
  const [choisi, setChoisi] = useState<Conducteur | null>(null);
  const [activites, setActivites] = useState<Activite[]>([]);
  const [compteurs, setCompteurs] = useState<Compteurs | null>(null);
  const [nouvelle, setNouvelle] = useState({ type: "conduite", debut: "", fin: "" });
  const [erreurActivite, setErreurActivite] = useState("");
  const dialogue = useRef<HTMLDialogElement>(null);

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

  async function ouvrirConduite(c: Conducteur) {
    setChoisi(c);
    setErreurActivite("");
    dialogue.current?.showModal();
    await rafraichir(c);
  }

  async function rafraichir(c: Conducteur) {
    setActivites(await (await fetch(`/api/admin/conducteurs/${c.id}/activites`)).json());
    setCompteurs(await (await fetch(`/api/admin/conducteurs/${c.id}/compteurs`)).json());
  }

  async function declarer(e: React.FormEvent) {
    e.preventDefault();
    setErreurActivite("");
    const r = await fetch(`/api/admin/conducteurs/${choisi!.id}/activites`, {
      method: "POST", headers: json,
      body: JSON.stringify({ activites: [{ type: nouvelle.type, debut: new Date(nouvelle.debut).toISOString(), fin: new Date(nouvelle.fin).toISOString() }] }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      return setErreurActivite(r.status === 409 ? "Cette activité chevauche une activité déjà déclarée." : typeof j.detail === "string" ? j.detail : "Activité invalide : vérifiez les dates (la fin après le début, 24 h au plus).");
    }
    setNouvelle({ ...nouvelle, debut: "", fin: "" });
    rafraichir(choisi!);
  }

  async function retirer(a: Activite) {
    await fetch(`/api/admin/conducteurs/${choisi!.id}/activites/${a.id}`, { method: "DELETE" });
    rafraichir(choisi!);
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
                    <button className="btn btn-ghost btn-sm" onClick={() => ouvrirConduite(c)}>Temps de conduite</button>
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

      <dialog ref={dialogue} className="dialog large" aria-labelledby="tc-titre">
        <div style={{ display: "grid", gap: 18, padding: 24 }}>
          <div>
            <h2 id="tc-titre">Temps de conduite de {choisi?.nom}</h2>
            <p className="muted" style={{ marginTop: 6 }}>Activités déclarées sur les 15 derniers jours. Elles servent à calculer ce que le conducteur peut encore conduire quand il est affecté à une tournée.</p>
          </div>
          {compteurs && (
            <dl className="indicateurs" style={{ marginBottom: 0 }}>
              <div><dt>Avant la prochaine pause</dt><dd>{duree(compteurs.conduite_continue_min)}</dd></div>
              <div><dt>Reste aujourd'hui</dt><dd>{duree(compteurs.conduite_jour_normale_min)}{compteurs.conduite_jour_min > compteurs.conduite_jour_normale_min && ` (jusqu'à ${duree(compteurs.conduite_jour_min)})`}</dd></div>
              <div><dt>Reste cette semaine</dt><dd>{duree(compteurs.conduite_semaine_min)}</dd></div>
              <div><dt>Extensions à 10 h</dt><dd>{compteurs.extensions_restantes}</dd></div>
            </dl>
          )}
          {compteurs?.infractions.map((i, n) => <div key={n} className="notice danger" style={{ margin: 0 }}><strong>{quand(i.debut)}</strong> · {i.message}</div>)}
          {compteurs?.notes.map((n, i) => <div key={i} className="notice" style={{ margin: 0 }}>{n}</div>)}

          <form onSubmit={declarer} className="form-grid">
            <div className="field"><label htmlFor="a-type">Type</label>
              <select id="a-type" className="select" value={nouvelle.type} onChange={(e) => setNouvelle({ ...nouvelle, type: e.target.value })}>{Object.entries(TYPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            </div>
            <div className="field"><label htmlFor="a-debut">Début</label><input id="a-debut" className="input" type="datetime-local" value={nouvelle.debut} onChange={(e) => setNouvelle({ ...nouvelle, debut: e.target.value })} required /></div>
            <div className="field"><label htmlFor="a-fin">Fin</label><input id="a-fin" className="input" type="datetime-local" value={nouvelle.fin} onChange={(e) => setNouvelle({ ...nouvelle, fin: e.target.value })} required /></div>
            <div style={{ alignSelf: "end" }}><button className="btn btn-primary" type="submit">Déclarer</button></div>
          </form>
          {erreurActivite && <div className="notice danger" role="alert" style={{ margin: 0 }}>{erreurActivite}</div>}

          <div className="scroll">
            <table className="rack">
              <thead><tr><th>Type</th><th>Début</th><th>Fin</th><th><span className="sr-only">Supprimer</span></th></tr></thead>
              <tbody>
                {activites.length === 0 && <tr><td colSpan={4} className="muted">Aucune activité déclarée : le conducteur est supposé reposé.</td></tr>}
                {activites.map((a) => (
                  <tr key={a.id}><td>{TYPES[a.type] ?? a.type}</td><td className="num">{quand(a.debut)}</td><td className="num">{quand(a.fin)}</td><td className="right"><button className="btn btn-ghost btn-sm" onClick={() => retirer(a)}>Supprimer</button></td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="dialog-actions"><button className="btn" onClick={() => dialogue.current?.close()}>Fermer</button></div>
        </div>
      </dialog>
    </>
  );
}
