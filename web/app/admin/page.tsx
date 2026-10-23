"use client";

import { CalendarDays, Clock, Truck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { dateHeure, Empty, Plaque, Statut, STATUT_LABELS, StatusBadge } from "../ui";

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

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Tableau de bord</h1>
          <p>État de la flotte {date && date !== aujourdhui() ? `le ${new Date(date).toLocaleDateString("fr-FR")}` : "aujourd'hui"}.</p>
        </div>
        <div className="input-icon">
          <CalendarDays aria-hidden />
          <input className="input" type="date" aria-label="Jour affiché" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
      </div>

      {rappels && rappels.vehicules.length > 0 && date === aujourdhui() && (
        <div className="alert alert-warn" role="status" style={{ marginBottom: 16 }}>
          <Clock aria-hidden />
          <span><strong>{rappels.vehicules.length} camion{rappels.vehicules.length > 1 ? "s" : ""} sans contrôle depuis {rappels.heure_rappel}</strong> : {rappels.vehicules.map((v) => v.plaque).join(", ")}</span>
        </div>
      )}

      <div className="tabs" role="group" aria-label="Filtrer par état">
        <button className="tab" aria-pressed={filtre === "tous"} onClick={() => setFiltre("tous")}>Tous <span className="count">{lignes.length}</span></button>
        {ORDRE.map((s) => (
          <button key={s} className="tab" aria-pressed={filtre === s} onClick={() => setFiltre(s)}>{STATUT_LABELS[s]} <span className="count">{compte(s)}</span></button>
        ))}
      </div>

      <div className="panel">
        {visibles.length === 0 ? (
          <Empty icon={<Truck aria-hidden />} title="Aucun camion à afficher">Aucun véhicule ne correspond à ce filtre.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table table-cards">
              <thead>
                <tr><th>Camion</th><th>État</th><th>Dernier contrôle</th><th><span className="sr-only">Actions</span></th></tr>
              </thead>
              <tbody>
                {visibles.map((l) => (
                  <tr key={l.vehicle_id}>
                    <td><Plaque>{l.plaque}</Plaque></td>
                    <td><StatusBadge statut={l.statut} /></td>
                    <td className="full">
                      {l.controle ? (
                        <Link className="cell-link" href={`/admin/controles/${l.controle.id}`}>{l.controle.conducteur}</Link>
                      ) : <span className="muted">Aucun ce jour</span>}
                      {l.controle && <span className="muted"> · {dateHeure(l.controle.created_at)}</span>}
                    </td>
                    <td className="right full">{l.statut === "bloque" && <button className="btn btn-sm" onClick={() => ouvrir(l)}>Débloquer</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <dialog ref={dialogue} className="dialog" aria-labelledby="debloquer-titre">
        <form onSubmit={debloquer}>
          <div>
            <h2 id="debloquer-titre">Débloquer {cible?.plaque}</h2>
            <p className="muted" style={{ marginTop: 4 }}>Le déblocage est enregistré avec votre nom, la date et ce commentaire.</p>
          </div>
          <div className="field">
            <label htmlFor="motif">Pourquoi débloquer ce camion ?</label>
            <textarea id="motif" className="textarea" rows={3} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} minLength={3} maxLength={1000} required />
          </div>
          {erreur && <div className="alert alert-danger" role="alert"><TriangleAlert aria-hidden /><span>{erreur}</span></div>}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => dialogue.current?.close()}>Annuler</button>
            <button type="submit" className="btn btn-primary" disabled={commentaire.trim().length < 3}>Débloquer le camion</button>
          </div>
        </form>
      </dialog>
    </>
  );
}
