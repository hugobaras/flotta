"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { dateHeure, Etat, Macaron, Plaque, Statut, STATUT_LABELS } from "../ui";

type Ligne = { vehicle_id: number; plaque: string; statut: Statut; controle: { id: number; conducteur: string; created_at: string } | null };
type Rappels = { heure_rappel: string; vehicules: { id: number; plaque: string }[] };

const aujourdhui = () => new Date().toLocaleDateString("sv-SE"); // AAAA-MM-JJ, jour local
const ORDRE: Statut[] = ["bloque", "defaut", "non_controle", "controle"];

export default function Admin() {
  const [date, setDate] = useState(aujourdhui);
  const [lignes, setLignes] = useState<Ligne[] | null>(null);
  const [rappels, setRappels] = useState<Rappels | null>(null);
  const [filtre, setFiltre] = useState<Statut | "tous">("tous");
  const [cible, setCible] = useState<Ligne | null>(null);
  const [commentaire, setCommentaire] = useState("");
  const [erreur, setErreur] = useState("");
  const dialogue = useRef<HTMLDialogElement>(null);

  const charger = useCallback(async () => {
    const r = await fetch(`/api/admin/tableau${date ? `?date=${date}` : ""}`);
    if (r.status === 401) return (window.location.href = "/connexion");
    setLignes((await r.json()).vehicules);
    setRappels(await (await fetch("/api/admin/rappels")).json());
  }, [date]);

  useEffect(() => {
    charger();
  }, [charger]);

  function ouvrir(l: Ligne) {
    setCible(l);
    setCommentaire("");
    setErreur("");
    dialogue.current?.showModal();
  }

  async function debloquer(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch(`/api/admin/vehicules/${cible!.vehicle_id}/debloquer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commentaire }),
    });
    if (!r.ok) return setErreur("Déblocage impossible. Vérifiez le commentaire et réessayez.");
    dialogue.current?.close();
    charger();
  }

  if (!lignes) return <p className="muted">Chargement…</p>;

  const compte = (s: Statut) => lignes.filter((l) => l.statut === s).length;
  const visibles = lignes
    .filter((l) => filtre === "tous" || l.statut === filtre)
    .sort((a, b) => ORDRE.indexOf(a.statut) - ORDRE.indexOf(b.statut) || a.plaque.localeCompare(b.plaque));
  const jourCourant = date === aujourdhui();

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Tableau de bord</h1>
          <p>État de la flotte {jourCourant ? "aujourd'hui" : `le ${new Date(date).toLocaleDateString("fr-FR")}`}.</p>
        </div>
        <input className="input" type="date" aria-label="Jour affiché" value={date} onChange={(e) => setDate(e.target.value || aujourdhui())} />
      </div>

      {rappels && rappels.vehicules.length > 0 && jourCourant && (
        <div className="notice" role="status">
          <span><strong>{rappels.vehicules.length} camion{rappels.vehicules.length > 1 ? "s" : ""} sans contrôle depuis {rappels.heure_rappel}</strong> : {rappels.vehicules.map((v) => v.plaque).join(", ")}</span>
        </div>
      )}

      <div className="filtres" role="group" aria-label="Filtrer par état">
        <button className="filtre" aria-pressed={filtre === "tous"} onClick={() => setFiltre("tous")}>Tous <span className="count">{lignes.length}</span></button>
        {ORDRE.map((s) => (
          <button key={s} className="filtre" aria-pressed={filtre === s} onClick={() => setFiltre(s)}>
            <Macaron statut={s} />{STATUT_LABELS[s]} <span className="count">{compte(s)}</span>
          </button>
        ))}
      </div>

      {visibles.length === 0 ? (
        <div className="rack-empty"><strong>Aucun camion</strong>Aucun véhicule ne correspond à ce filtre.</div>
      ) : (
        <div className="table-wrap">
          <table className="rack rack-cards">
            <thead>
              <tr><th>Camion</th><th>État</th><th>Dernier contrôle</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {visibles.map((l) => (
                <tr key={l.vehicle_id}>
                  <td><Plaque size="lg">{l.plaque}</Plaque></td>
                  <td><Etat statut={l.statut} /></td>
                  <td className="full">
                    {l.controle ? (
                      <>
                        <Link className="cell-link" href={`/admin/controles/${l.controle.id}`}>{l.controle.conducteur}</Link>
                        <span className="muted"> · {dateHeure(l.controle.created_at)}</span>
                      </>
                    ) : <span className="muted">Aucun contrôle ce jour</span>}
                  </td>
                  <td className="right full">{l.statut === "bloque" && <button className="btn btn-sm" onClick={() => ouvrir(l)}>Débloquer</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <dialog ref={dialogue} className="dialog" aria-labelledby="debloquer-titre">
        <form onSubmit={debloquer}>
          <div>
            <h2 id="debloquer-titre">Débloquer {cible && <Plaque>{cible.plaque}</Plaque>}</h2>
            <p className="muted" style={{ marginTop: 8 }}>Le déblocage est enregistré avec votre nom, la date et ce commentaire.</p>
          </div>
          <div className="field">
            <label htmlFor="motif">Pourquoi débloquer ce camion ?</label>
            <textarea id="motif" className="textarea" rows={3} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} minLength={3} maxLength={1000} required />
          </div>
          {erreur && <div className="notice danger" role="alert" style={{ margin: 0 }}>{erreur}</div>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => dialogue.current?.close()}>Annuler</button>
            <button type="submit" className="btn btn-primary" disabled={commentaire.trim().length < 3}>Débloquer le camion</button>
          </div>
        </form>
      </dialog>
    </>
  );
}
