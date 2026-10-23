"use client";

import { Check, TriangleAlert, Upload } from "lucide-react";
import { useEffect, useState } from "react";

type Params = { heure_rappel: string; retention_jours: number; alert_emails: string[]; logo: boolean };
type Message = { ok: boolean; texte: string } | null;

export default function Parametres() {
  const [p, setP] = useState<Params | null>(null);
  const [emails, setEmails] = useState("");
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => {
    fetch("/api/admin/parametres").then(async (r) => {
      if (r.status === 401) return (window.location.href = "/connexion");
      const data: Params = await r.json();
      setP(data);
      setEmails(data.alert_emails.join("\n"));
    });
  }, []);

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    const alert_emails = emails.split("\n").map((x) => x.trim()).filter(Boolean);
    const r = await fetch("/api/admin/parametres", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ heure_rappel: p!.heure_rappel, retention_jours: p!.retention_jours, alert_emails }),
    });
    setMessage(r.ok ? { ok: true, texte: "Paramètres enregistrés." }
      : { ok: false, texte: r.status === 403 ? "Réservé aux administrateurs." : "Valeurs invalides : vérifiez les adresses email et les durées." });
    if (r.ok) setP(await r.json());
  }

  async function envoyerLogo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const form = new FormData();
    form.append("logo", f);
    const r = await fetch("/api/admin/logo", { method: "POST", body: form });
    setMessage(r.ok ? { ok: true, texte: "Logo enregistré." }
      : { ok: false, texte: r.status === 403 ? "Réservé aux administrateurs." : "Logo refusé : JPEG ou PNG, 1 Mo maximum." });
    if (r.ok) setP({ ...p!, logo: true });
    e.target.value = "";
  }

  if (!p) return <p className="muted">Chargement…</p>;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Paramètres</h1>
          <p>Alertes, rappels et conservation des données de votre société.</p>
        </div>
      </div>

      {message && (
        <div className={`alert ${message.ok ? "alert-ok" : "alert-danger"}`} role="status" style={{ marginBottom: 16 }}>
          {message.ok ? <Check aria-hidden /> : <TriangleAlert aria-hidden />}<span>{message.texte}</span>
        </div>
      )}

      <div className="stack-lg" style={{ maxWidth: 680 }}>
        <form className="panel" onSubmit={enregistrer}>
          <div className="panel-head"><h2>Alertes et rappels</h2></div>
          <div className="panel-body stack">
            <div className="field">
              <label htmlFor="emails">Destinataires des alertes</label>
              <textarea id="emails" className="textarea" rows={3} value={emails} onChange={(e) => setEmails(e.target.value)} />
              <span className="hint">Un email par ligne, 10 au maximum. Ils reçoivent l'alerte de défaut critique et le rappel quotidien.</span>
            </div>
            <div className="field">
              <label htmlFor="heure">Heure du rappel</label>
              <input id="heure" className="input" style={{ maxWidth: 200 }} type="time" value={p.heure_rappel} onChange={(e) => setP({ ...p, heure_rappel: e.target.value })} required />
              <span className="hint">Camions sans contrôle à cette heure, heure de Paris.</span>
            </div>
            <div className="field">
              <label htmlFor="retention">Conservation (jours)</label>
              <input id="retention" className="input" style={{ maxWidth: 200 }} type="number" min={30} max={3650} value={p.retention_jours} onChange={(e) => setP({ ...p, retention_jours: Number(e.target.value) })} required />
              <span className="hint">Contrôles, photos et positions sont supprimés passé ce délai (3 ans par défaut).</span>
            </div>
            <div><button className="btn btn-primary" type="submit">Enregistrer</button></div>
          </div>
        </form>

        <section className="panel" aria-labelledby="logo">
          <div className="panel-head"><h2 id="logo">Logo</h2></div>
          <div className="panel-body stack">
            {p.logo && <img src="/api/admin/logo" alt="Logo actuel" style={{ height: 48, width: "fit-content", maxWidth: "100%", objectFit: "contain" }} />}
            <div>
              <label className="btn" style={{ cursor: "pointer" }}>
                <Upload aria-hidden />{p.logo ? "Remplacer le logo" : "Choisir un logo"}
                <input className="sr-only" type="file" accept="image/png,image/jpeg" onChange={envoyerLogo} />
              </label>
            </div>
            <span className="hint">Affiché en tête des PDF de contrôle. JPEG ou PNG, 1 Mo maximum.</span>
          </div>
        </section>
      </div>
    </>
  );
}
