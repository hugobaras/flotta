"use client";

import { useState } from "react";

export default function Connexion() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erreur, setErreur] = useState("");

  async function envoyer(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (r.ok) return (window.location.href = "/admin");
    setErreur(r.status === 429 ? "Trop de tentatives, réessayez plus tard." : "Identifiants invalides.");
  }

  return (
    <main>
      <h1>Connexion</h1>
      <form onSubmit={envoyer} style={{ display: "grid", gap: 8 }}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Mot de passe" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit">Se connecter</button>
      </form>
      {erreur && <p role="alert">{erreur}</p>}
    </main>
  );
}
