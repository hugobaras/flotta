"use client";

import { useState } from "react";
import { BandeauPublic } from "../ui";

export default function Connexion() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  async function envoyer(e: React.FormEvent) {
    e.preventDefault();
    setEnvoi(true);
    setErreur("");
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (r.ok) return (window.location.href = "/admin");
      setErreur(r.status === 429 ? "Trop de tentatives. Réessayez dans quelques minutes." : "Email ou mot de passe incorrect.");
    } catch {
      setErreur("Connexion impossible. Vérifiez votre réseau et réessayez.");
    }
    setEnvoi(false);
  }

  return (
    <div className="public">
      <BandeauPublic />
      <main className="public-body">
        <div className="auth">
          <h1>Connexion</h1>
          <form onSubmit={envoyer}>
            <div className="field">
              <label htmlFor="email">Adresse email</label>
              <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
            </div>
            <div className="field">
              <label htmlFor="password">Mot de passe</label>
              <input id="password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            {erreur && <div className="notice danger" role="alert" style={{ margin: 0 }}>{erreur}</div>}
            <button className="btn btn-primary" type="submit" disabled={envoi}>{envoi ? "Connexion…" : "Se connecter"}</button>
          </form>
        </div>
      </main>
    </div>
  );
}
