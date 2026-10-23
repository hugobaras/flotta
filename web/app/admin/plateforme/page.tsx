"use client";

import { useCallback, useEffect, useState } from "react";

type Societe = { id: number; nom: string; camions_actifs: number; utilisateurs: number; offre: string | null; camions_factures: number | null; statut: string | null; mensuel_ht?: number };
type Tableau = { mrr_ht: number; camions_factures: number; clients_actifs: number; clients_en_essai: number; clients_suspendus: number };

const json = { "Content-Type": "application/json" };
const eur = (c: number) => (c / 100).toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
const STATUTS: Record<string, string> = { essai: "Essai", actif: "Actif", suspendu: "Suspendu" };

export default function Plateforme() {
  const [societes, setSocietes] = useState<Societe[] | null>(null);
  const [tableau, setTableau] = useState<Tableau | null>(null);
  const [message, setMessage] = useState("");
  const [nouvelle, setNouvelle] = useState({ nom: "", offre: "essentiel", camions_factures: 10 });

  const charger = useCallback(async () => {
    const [s, t] = await Promise.all([fetch("/api/plateforme/societes"), fetch("/api/plateforme/tableau")]);
    if (s.status === 403) return setMessage("Cette page est réservée à l'équipe Flotta.");
    setSocietes(await s.json());
    setTableau(await t.json());
  }, []);
  useEffect(() => { charger(); }, [charger]);

  async function creer(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch("/api/plateforme/societes", { method: "POST", headers: json, body: JSON.stringify({ ...nouvelle, statut: "essai" }) });
    setMessage(r.ok ? "Société créée en essai. Créez son premier compte avec create_user.py." : "Valeurs invalides.");
    if (r.ok) { setNouvelle({ nom: "", offre: "essentiel", camions_factures: 10 }); charger(); }
  }

  async function modifier(id: number, patch: object) {
    await fetch(`/api/plateforme/societes/${id}/abonnement`, { method: "PATCH", headers: json, body: JSON.stringify(patch) });
    charger();
  }

  async function document(id: number, type: "devis" | "facture", periode: "mensuel" | "annuel") {
    const r = await fetch(`/api/plateforme/societes/${id}/documents`, { method: "POST", headers: json, body: JSON.stringify({ type, periode }) });
    if (!r.ok) return setMessage("Émission impossible : la société n'a pas d'abonnement.");
    const d = await r.json();
    setMessage(`${d.numero} émis (${eur(d.ttc)} TTC).`);
    window.open(`/api/plateforme/documents/${d.id}/pdf`, "_blank");
  }

  return (
    <>
      <div className="page-head"><div><h1>Plateforme</h1><p className="muted">Sociétés clientes, offres et facturation.</p></div></div>
      {message && <div className="notice" role="status">{message}</div>}
      {tableau && (
        <dl className="indicateurs">
          <div><dt>MRR (HT)</dt><dd className="num">{eur(tableau.mrr_ht)}</dd></div>
          <div><dt>Camions facturés</dt><dd className="num">{tableau.camions_factures}</dd></div>
          <div><dt>Clients actifs</dt><dd className="num">{tableau.clients_actifs}</dd></div>
          <div><dt>En essai</dt><dd className="num">{tableau.clients_en_essai}</dd></div>
        </dl>
      )}
      <div className="table-wrap"><table className="table" aria-label="Sociétés">
        <thead><tr><th>Société</th><th>Offre</th><th>Camions facturés</th><th>Camions actifs</th><th>Statut</th><th>Mensuel HT</th><th><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>
          {societes?.map((s) => (
            <tr key={s.id}>
              <td>{s.nom}</td>
              <td>
                <select className="select" aria-label={`Offre de ${s.nom}`} value={s.offre ?? ""} onChange={(e) => modifier(s.id, { offre: e.target.value })}>
                  {!s.offre && <option value="">Aucune</option>}
                  <option value="essentiel">Essentiel</option><option value="pro">Pro</option>
                </select>
              </td>
              <td><input className="input num" style={{ width: 80 }} type="number" min={1} aria-label={`Camions facturés de ${s.nom}`} defaultValue={s.camions_factures ?? ""} onBlur={(e) => e.target.value && Number(e.target.value) !== s.camions_factures && modifier(s.id, { camions_factures: Number(e.target.value) })} /></td>
              <td className="num">{s.camions_actifs}</td>
              <td>
                <select className="select" aria-label={`Statut de ${s.nom}`} value={s.statut ?? ""} onChange={(e) => modifier(s.id, { statut: e.target.value })}>
                  {!s.statut && <option value="">—</option>}
                  {Object.entries(STATUTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </td>
              <td className="num">{s.mensuel_ht !== undefined ? eur(s.mensuel_ht) : "—"}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                {s.offre && <>
                  <button className="btn btn-ghost btn-sm" onClick={() => document(s.id, "devis", "mensuel")}>Devis</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => document(s.id, "facture", "mensuel")}>Facture du mois</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => document(s.id, "facture", "annuel")}>Facture annuelle</button>
                </>}
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <form onSubmit={creer} className="barre-outils" style={{ marginTop: 24 }}>
        <input className="input" required placeholder="Nom de la société" aria-label="Nom de la société" value={nouvelle.nom} onChange={(e) => setNouvelle({ ...nouvelle, nom: e.target.value })} />
        <select className="select" style={{ width: "auto" }} aria-label="Offre" value={nouvelle.offre} onChange={(e) => setNouvelle({ ...nouvelle, offre: e.target.value })}>
          <option value="essentiel">Essentiel</option><option value="pro">Pro</option>
        </select>
        <input className="input num" style={{ width: 90 }} type="number" min={1} aria-label="Camions facturés" value={nouvelle.camions_factures} onChange={(e) => setNouvelle({ ...nouvelle, camions_factures: Number(e.target.value) })} />
        <button className="btn btn-primary">Créer la société</button>
      </form>
    </>
  );
}
