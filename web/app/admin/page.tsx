"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Panneau } from "./panneau";
import Controles from "./_sections/controles";
import { Coche, dateHeure, Etat, Macaron, Plaque, Statut } from "../ui";

type Ligne = { vehicle_id: number; plaque: string; statut: Statut; controle: { id: number; conducteur: string; created_at: string } | null };
type Rappels = { heure_rappel: string; vehicules: { id: number; plaque: string }[] };
type Journee = { commandes: number; aPlanifier: number; plan: { id: number; statut: string; publie_le?: string | null; resume: { nb_tournees: number; nb_commandes: number; nb_non_affectees: number; km: number; nb_alertes: number } | null } | null };
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
  const [aFaire, setAFaire] = useState(0);

  const charger = useCallback(async () => {
    const r = await fetch(`/api/admin/tableau${date ? `?date=${date}` : ""}`);
    if (r.status === 401) return (window.location.href = "/connexion");
    setLignes((await r.json()).vehicules);
    setRappels(await (await fetch("/api/admin/rappels")).json());
    const [c, p] = await Promise.all([fetch(`/api/admin/commandes?date=${date}`), fetch("/api/admin/plans")]);
    if (c.ok && p.ok) {
      const cmds: { statut: string }[] = await c.json();
      // Le plan que suivent les chauffeurs (publié) d'abord, sinon le dernier calculé, sinon le dernier tenté.
      const du_jour: (NonNullable<Journee["plan"]> & { jour: string; publie_le: string | null })[] = (await p.json()).filter((x: { jour: string; archive: boolean }) => x.jour === date && !x.archive);
      const plan = du_jour.find((x) => x.publie_le) ?? du_jour.find((x) => x.statut === "termine") ?? du_jour[0] ?? null;
      setJournee({ commandes: cmds.length, aPlanifier: cmds.filter((x) => x.statut === "a_planifier").length, plan });
    }
  }, [date]);

  useEffect(() => {
    fetch("/api/admin/demarrage").then(async (r) => r.ok && setAFaire((await r.json()).etapes.filter((e: { fait: boolean | null }) => e.fait === false).length));
  }, []);

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
          <h1>Aujourd'hui</h1>
          <p>État de la flotte {jourCourant ? "aujourd'hui" : `le ${new Date(date).toLocaleDateString("fr-FR")}`}.</p>
        </div>
        <input className="input" type="date" aria-label="Jour affiché" value={date} onChange={(e) => setDate(e.target.value || aujourdhui())} />
      </div>

      {journee && (() => {
        const total = lignes.length;
        const bloques = lignes.filter((l) => l.statut === "bloque").length;
        const p = journee.plan;
        const resume = p?.statut === "termine" && p.resume ? `${p.resume.nb_tournees} tournée${p.resume.nb_tournees > 1 ? "s" : ""}${p.resume.nb_non_affectees ? ` · ${p.resume.nb_non_affectees} commande${p.resume.nb_non_affectees > 1 ? "s" : ""} sans camion` : ""}${p.resume.nb_alertes ? ` · ${p.resume.nb_alertes} point${p.resume.nb_alertes > 1 ? "s" : ""} à vérifier` : ""}` : "";
        type Etape = { fait: boolean; titre: string; detail?: string; lien: string; action: string };
        const etapes: Etape[] = [
          { fait: total > 0 && controles.length === total, titre: total === 0 ? "Aucun camion" : `${controles.length} camion${controles.length > 1 ? "s" : ""} sur ${total} contrôlé${controles.length > 1 ? "s" : ""}`, detail: bloques ? `${bloques} bloqué${bloques > 1 ? "s" : ""}, à débloquer ci-dessous` : rappels && rappels.vehicules.length > 0 && jourCourant ? `Pas de contrôle depuis ${rappels.heure_rappel} : ${rappels.vehicules.length <= 3 ? rappels.vehicules.map((v) => v.plaque).join(", ") : `${rappels.vehicules.length} camions`}` : undefined, lien: total === 0 ? "/admin/configuration#flotte" : "#liste", action: total === 0 ? "Ajouter des camions" : "Voir la liste" },
          { fait: journee.commandes > 0, titre: journee.commandes ? `${journee.commandes} commande${journee.commandes > 1 ? "s" : ""} à livrer` : "Aucune commande pour ce jour", lien: "/admin/planning#commandes", action: journee.commandes ? "Voir" : "Importer un fichier" },
          { fait: !!p?.publie_le, titre: p?.publie_le ? "Plan envoyé aux chauffeurs" : !p ? "Pas encore de plan" : p.statut === "echec" ? "Le dernier calcul a échoué" : p.statut === "termine" ? "Plan prêt, pas encore envoyé aux chauffeurs" : "Calcul en cours…", detail: resume || undefined, lien: "/admin/planning", action: !p ? "Calculer les tournées" : p.statut === "echec" ? "Relancer" : p.publie_le ? "Ouvrir" : "Vérifier et envoyer" },
        ];
        const premier = etapes.findIndex((e, i) => i > 0 && !e.fait);
        return (
          <section aria-label="Ma journée" className="journee">
            {etapes.map((e, i) => (
              <div key={i} className="journee-ligne" data-fait={e.fait || undefined}>
                <span className="journee-point" aria-hidden>{e.fait ? <Coche ok /> : null}</span>
                <div>
                  <strong>{e.titre}</strong>
                  {e.detail && <span className="muted">{e.detail}</span>}
                </div>
                <Link className={i === premier ? "btn btn-primary" : "btn btn-ghost btn-sm"} href={e.lien}>{e.action}</Link>
              </div>
            ))}
            {aFaire > 0 && jourCourant && <p className="hint">Mise en route : {aFaire} étape{aFaire > 1 ? "s" : ""} de configuration restante{aFaire > 1 ? "s" : ""} · <Link href="/admin/configuration#demarrer">Continuer</Link></p>}
          </section>
        );
      })()}

      <div id="liste" className="filtres" role="group" aria-label="Afficher">
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
      <div style={{ marginTop: 40 }}>
        <Panneau id="controles" titre="Historique des contrôles"><Controles /></Panneau>
      </div>
    </>
  );
}
