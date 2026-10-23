"use client";

import { useCallback, useEffect, useState } from "react";
import { ReglagesTabs } from "../../ui";

type Cle = { id: number; nom: string; apercu: string; derniere_utilisation: string | null; revoquee: boolean };
type Hook = { id: number; url: string; evenements: string[]; actif: boolean };
type Livraison = { id: number; evenement: string; statut: string; tentatives: number; derniere_erreur: string | null };

const json = { "Content-Type": "application/json" };
const LIBELLES: Record<string, string> = { "plan.publie": "Plan publié", "arret.livre": "Arrêt livré", "controle.defaut_critique": "Défaut critique" };
const STATUTS: Record<string, string> = { ok: "Reçu", en_attente: "En attente", echec: "Abandonné" };

export default function Integrations() {
  const [cles, setCles] = useState<Cle[]>([]);
  const [hooks, setHooks] = useState<Hook[]>([]);
  const [dispo, setDispo] = useState<string[]>([]);
  const [secret, setSecret] = useState("");
  const [erreur, setErreur] = useState("");
  const [nom, setNom] = useState("");
  const [url, setUrl] = useState("");
  const [choix, setChoix] = useState<string[]>([]);
  const [histo, setHisto] = useState<{ id: number; liste: Livraison[] } | null>(null);

  const charger = useCallback(async () => {
    const [c, h] = await Promise.all([fetch("/api/admin/integrations/cles"), fetch("/api/admin/integrations/webhooks")]);
    if (c.status === 401) return (window.location.href = "/connexion");
    if (!c.ok) return setErreur((await c.json().catch(() => ({}))).detail ?? "Indisponible.");
    setCles(await c.json());
    const j = await h.json();
    setHooks(j.webhooks.filter((w: Hook) => w.actif));
    setDispo(j.evenements_disponibles);
  }, []);
  useEffect(() => { charger(); }, [charger]);

  async function creerCle(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch("/api/admin/integrations/cles", { method: "POST", headers: json, body: JSON.stringify({ nom }) });
    const j = await r.json();
    if (!r.ok) return setErreur(j.detail ?? "Impossible de créer la clé.");
    setSecret(j.cle);
    setNom("");
    charger();
  }

  async function creerHook(e: React.FormEvent) {
    e.preventDefault();
    setErreur("");
    const r = await fetch("/api/admin/integrations/webhooks", { method: "POST", headers: json, body: JSON.stringify({ url, evenements: choix }) });
    const j = await r.json();
    if (!r.ok) return setErreur(typeof j.detail === "string" ? j.detail : "Adresse ou événements invalides.");
    setSecret(j.secret);
    setUrl("");
    setChoix([]);
    charger();
  }

  async function historique(id: number) {
    setHisto({ id, liste: await (await fetch(`/api/admin/integrations/webhooks/${id}/livraisons`)).json() });
  }

  return (
    <>
      <div className="page-head"><div><h1>Réglages</h1><p className="muted">Clés API et webhooks pour relier Flotta à votre logiciel de transport.</p></div></div>
      <ReglagesTabs actif="integrations" />
      {erreur && <div className="notice danger" role="alert">{erreur}</div>}
      {secret && (
        <div className="notice" role="status">
          <strong>Copiez-le maintenant, il ne sera plus affiché :</strong>
          <p className="num" style={{ wordBreak: "break-all", margin: "6px 0 0" }}>{secret}</p>
          <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => setSecret("")}>J'ai copié</button>
        </div>
      )}
      <section style={{ marginTop: 24 }}>
        <h2>Clés API</h2>
        <ul className="liste">
          {cles.map((k) => (
            <li key={k.id} style={{ display: "flex", gap: 12, alignItems: "center", padding: "10px 0" }}>
              <span style={{ flex: 1 }}><strong>{k.nom}</strong> <span className="num muted">{k.apercu}…</span>{k.revoquee && <span className="muted"> · révoquée</span>}
                <span className="muted"> · {k.derniere_utilisation ? `utilisée le ${new Date(k.derniere_utilisation).toLocaleDateString("fr-FR")}` : "jamais utilisée"}</span></span>
              {!k.revoquee && <button className="btn btn-ghost btn-sm" onClick={async () => { await fetch(`/api/admin/integrations/cles/${k.id}`, { method: "DELETE" }); charger(); }}>Révoquer</button>}
            </li>
          ))}
        </ul>
        <form onSubmit={creerCle} className="barre-outils">
          <input className="input" required placeholder="Nom (par exemple : TMS)" aria-label="Nom de la clé" value={nom} onChange={(e) => setNom(e.target.value)} />
          <button className="btn btn-primary">Créer une clé</button>
        </form>
        <p className="hint">Documentation : <a href="/api/v1/docs">/api/v1/docs</a>. Limite : 120 requêtes par minute et par clé.</p>
      </section>
      <section style={{ marginTop: 32 }}>
        <h2>Webhooks</h2>
        <ul className="liste">
          {hooks.map((w) => (
            <li key={w.id} style={{ padding: "10px 0" }}>
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <span style={{ flex: 1 }}><strong className="num">{w.url}</strong><br /><span className="muted">{w.evenements.map((e) => LIBELLES[e] ?? e).join(", ")}</span></span>
                <button className="btn btn-ghost btn-sm" onClick={() => historique(w.id)}>Historique</button>
                <button className="btn btn-ghost btn-sm" onClick={async () => { await fetch(`/api/admin/integrations/webhooks/${w.id}`, { method: "DELETE" }); charger(); }}>Supprimer</button>
              </div>
              {histo?.id === w.id && (
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {histo.liste.length === 0 && <li className="muted">Aucun envoi.</li>}
                  {histo.liste.map((l) => <li key={l.id}>{LIBELLES[l.evenement] ?? l.evenement} : {STATUTS[l.statut]} ({l.tentatives} essai{l.tentatives > 1 ? "s" : ""}){l.derniere_erreur && l.statut !== "ok" ? ` · ${l.derniere_erreur}` : ""}</li>)}
                </ul>
              )}
            </li>
          ))}
        </ul>
        <form onSubmit={creerHook} style={{ display: "grid", gap: 10, maxWidth: 560 }}>
          <input className="input" required type="url" placeholder="https://votre-logiciel.fr/webhooks/flotta" aria-label="Adresse du webhook" value={url} onChange={(e) => setUrl(e.target.value)} />
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {dispo.map((e) => (
              <label key={e} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={choix.includes(e)} onChange={(ev) => setChoix(ev.target.checked ? [...choix, e] : choix.filter((x) => x !== e))} />{LIBELLES[e] ?? e}
              </label>
            ))}
          </div>
          <div><button className="btn btn-primary" disabled={!choix.length}>Ajouter le webhook</button></div>
        </form>
        <p className="hint">Adresse HTTPS publique uniquement. Chaque envoi est signé ; réessais pendant environ 15 heures en cas d'échec.</p>
      </section>
    </>
  );
}
