"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { dateHeure, Etat, Macaron, Plaque, Statut } from "../ui";

type Ligne = { vehicle_id: number; plaque: string; statut: Statut; controle: { id: number; conducteur: string; created_at: string } | null };
type Rappels = { heure_rappel: string; vehicules: { id: number; plaque: string }[] };
type Journee = { commandes: number; aPlanifier: number; plan: { id: number; statut: string; resume: { nb_tournees: number; nb_commandes: number; nb_non_affectees: number; km: number; nb_alertes: number } | null } | null };
type Filtre = "traiter" | "controle" | "tous";

const aujourdhui = () => new Date().toLocaleDateString("sv-SE"); // AAAA-MM-JJ, jour local
const ORDRE: Statut[] = ["bloque", "defaut", "non_controle", "controle"];
const MOTIFS = ["Défaut réparé", "Fausse alerte", "Vérifié par le garage"];

export default function Admin() {
  const [date, setDate] = useState(aujourdhui);
  const [lignes, setLignes] = useState<Ligne[] | null>(null);
  const [rappels, setRappels] = useState<Rappels | null>(null);
  const [journee, setJournee] = useState<Journee | null>(null);
  const [filtre, setFiltre] = useState<Filtre>("traiter");
  const [ouvert, setOuvert] = useState<number | null>(null);
  const [motif, setMotif] = useState("");
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    const r = await fetch(`/api/admin/tableau${date ? `?date=${date}` : ""}`);
    if (r.status === 401) return (window.location.href = "/connexion");
    setLignes((await r.json()).vehicules);
    setRappels(await (await fetch("/api/admin/rappels")).json());
    const [c, p] = await Promise.all([fetch(`/api/admin/commandes?date=${date}`), fetch("/api/admin/plans")]);
    if (c.ok && p.ok) {
      const cmds: { statut: string }[] = await c.json();
      const plan = (await p.json()).find((x: { jour: string }) => x.jour === date) ?? null;
      setJournee({ commandes: cmds.length, aPlanifier: cmds.filter((x) => x.statut === "a_planifier").length, plan });
    }
  }, [date]);

  useEffect(() => {
    charger();
  }, [charger]);

  function ouvrir(id: number) {
    setOuvert(ouvert === id ? null : id);
    setMotif("");
    setErreur("");
  }

  async function debloquer(e: React.FormEvent, id: number) {
    e.preventDefault();
    const r = await fetch(`/api/admin/vehicules/${id}/debloquer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commentaire: motif }),
    });
    if (!r.ok) return setErreur("Déblocage impossible. Vérifiez le motif et réessayez.");
    setOuvert(null);
    charger();
  }

  if (!lignes) return <p className="muted">Chargement…</p>;

  const aTraiter = lignes.filter((l) => l.statut !== "controle");
  const controles = lignes.filter((l) => l.statut === "controle");
  const visibles = (filtre === "traiter" ? aTraiter : filtre === "controle" ? controles : lignes)
    .slice()
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

      {journee && (
        <section aria-label="Livraisons du jour" style={{ marginBottom: 28 }}>
          {journee.commandes === 0 ? (
            <p className="muted">Aucune commande ce jour. <Link href="/admin/commandes">Importer des commandes</Link></p>
          ) : (
            <dl className="indicateurs" style={{ marginBottom: 8 }}>
              <div><dt>Commandes</dt><dd className="num">{journee.commandes}</dd></div>
              <div><dt>Tournées</dt><dd className="num">{journee.plan?.resume?.nb_tournees ?? "—"}</dd></div>
              <div><dt>Non affectées</dt><dd className="num">{journee.plan?.resume ? journee.plan.resume.nb_non_affectees : journee.aPlanifier}</dd></div>
              <div><dt>Alertes du plan</dt><dd className="num">{journee.plan?.resume?.nb_alertes ?? "—"}</dd></div>
            </dl>
          )}
          {journee.commandes > 0 && <p className="hint">{journee.plan ? <Link href="/admin/planning">Ouvrir le planning</Link> : <>Pas encore de plan : <Link href="/admin/planning">lancer l'optimisation</Link></>} · <Link href="/admin/commandes">Voir les commandes</Link></p>}
        </section>
      )}

      <div className="filtres" role="group" aria-label="Afficher">
        <button className="filtre" aria-pressed={filtre === "traiter"} onClick={() => setFiltre("traiter")}>À traiter <span className="count">{aTraiter.length}</span></button>
        <button className="filtre" aria-pressed={filtre === "controle"} onClick={() => setFiltre("controle")}><Macaron statut="controle" />Contrôlés <span className="count">{controles.length}</span></button>
        <button className="filtre" aria-pressed={filtre === "tous"} onClick={() => setFiltre("tous")}>Tous <span className="count">{lignes.length}</span></button>
      </div>

      {visibles.length === 0 ? (
        <div className="rack-empty">
          <strong>{filtre === "traiter" ? "Tout est en ordre" : "Aucun camion"}</strong>
          {filtre === "traiter" ? "Aucun camion bloqué, en défaut ou sans contrôle." : "Aucun véhicule dans cette liste."}
        </div>
      ) : (
        <div className="table-wrap">
          <table className="rack rack-cards">
            <thead>
              <tr><th>Camion</th><th>État</th><th>Dernier contrôle</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {visibles.map((l) => (
                <Fragment key={l.vehicle_id}>
                  <tr>
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
                    <td className="right full">
                      {l.statut === "bloque" && (
                        <button className="btn btn-primary btn-sm" aria-expanded={ouvert === l.vehicle_id} onClick={() => ouvrir(l.vehicle_id)}>Débloquer</button>
                      )}
                    </td>
                  </tr>
                  {ouvert === l.vehicle_id && (
                    <tr className="deblocage">
                      <td colSpan={4} className="full">
                        <form onSubmit={(e) => debloquer(e, l.vehicle_id)}>
                          <div className="chips" role="group" aria-label="Motifs fréquents">
                            {MOTIFS.map((m) => <button type="button" key={m} className="chip" onClick={() => setMotif(m)}>{m}</button>)}
                          </div>
                          <div className="row">
                            <input className="input" aria-label={`Motif du déblocage de ${l.plaque}`} placeholder="Motif du déblocage (obligatoire)" value={motif} onChange={(e) => setMotif(e.target.value)} minLength={3} maxLength={1000} required autoFocus />
                            <button type="submit" className="btn btn-primary" disabled={motif.trim().length < 3}>Confirmer</button>
                            <button type="button" className="btn" onClick={() => setOuvert(null)}>Annuler</button>
                          </div>
                          {erreur && <p role="alert" style={{ color: "var(--rouge)", fontWeight: 500 }}>{erreur}</p>}
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
