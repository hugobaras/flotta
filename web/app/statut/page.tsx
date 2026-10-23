"use client";

import { useEffect, useState } from "react";
import { BandeauPublic } from "../ui";

export default function Statut() {
  const [etat, setEtat] = useState<"verif" | "ok" | "ko">("verif");
  const [heure, setHeure] = useState("");
  useEffect(() => {
    async function verifier() {
      try {
        const r = await fetch("/api/health", { cache: "no-store" });
        setEtat(r.ok ? "ok" : "ko");
      } catch {
        setEtat("ko");
      }
      setHeure(new Date().toLocaleTimeString("fr-FR"));
    }
    verifier();
    const t = setInterval(verifier, 30000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="public">
      <BandeauPublic />
      <main className="public-body">
        <div className="auth">
          <h1>État du service</h1>
          <p role="status" style={{ fontSize: 18 }}>
            {etat === "verif" ? "Vérification…" : etat === "ok" ? "Flotta fonctionne normalement." : "Flotta rencontre un incident. Nous y travaillons."}
          </p>
          {heure && <p className="hint">Dernière vérification à {heure}. Les contrôles déjà remplis sur un téléphone sont conservés et envoyés dès le retour du réseau.</p>}
        </div>
      </main>
    </div>
  );
}
