export type Statut = "controle" | "non_controle" | "defaut" | "bloque";

export const STATUT_LABELS: Record<Statut, string> = {
  controle: "Contrôlé", non_controle: "Non contrôlé", defaut: "Défaut", bloque: "Bloqué",
};

// Un état se lit par son point ET son texte, jamais par la couleur seule.
export function Macaron({ statut, size }: { statut: Statut; size?: "lg" | "xl" }) {
  if (size === "xl") {
    return (
      <svg className="mark" viewBox="0 0 64 64" aria-hidden fill="none" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="32" cy="32" r="30" className={`mark-ring mark-${statut}`} strokeWidth="2" />
        <path className={`mark-${statut}`} strokeWidth="3.5" d={statut === "controle" ? "M20 33 L28 41 L44 24" : statut === "non_controle" ? "M21 32 H43" : "M23 23 L41 41 M41 23 L23 41"} />
      </svg>
    );
  }
  return <span className={`dot dot-${statut}`} aria-hidden />;
}

export function Etat({ statut, label }: { statut: Statut; label?: string }) {
  return <span className="etat"><Macaron statut={statut} />{label ?? STATUT_LABELS[statut]}</span>;
}

// Plaque : simple chasse fixe dans un filet, sans imitation de la vraie plaque.
export function Plaque({ children, size }: { children: string; size?: "lg" | "xl" }) {
  return <span className={`plaque ${size ? `plaque-${size}` : ""}`}>{children}</span>;
}

export function Brand({ href }: { href?: string }) {
  const contenu = <><span className="brand-mark" aria-hidden />Flotta</>;
  return href ? <a className="brand" href={href}>{contenu}</a> : <div className="brand">{contenu}</div>;
}

export function Coche({ ok }: { ok: boolean }) {
  return (
    <svg className={`coche ${ok ? "coche-ok" : "coche-ko"}`} viewBox="0 0 16 16" width="16" height="16" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" role="img" aria-label={ok ? "Conforme" : "Défaut"}>
      <path d={ok ? "M3 8.5 L6.5 12 L13 4.5" : "M4 4 L12 12 M12 4 L4 12"} stroke="currentColor" />
    </svg>
  );
}

export function Cadenas({ ferme }: { ferme: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="7" width="10" height="7" rx="1.5" />
      <path d={ferme ? "M5.5 7V5a2.5 2.5 0 0 1 5 0v2" : "M5.5 7V5a2.5 2.5 0 0 1 4.6-1.3"} />
    </svg>
  );
}

export function Chevron({ sens }: { sens: "haut" | "bas" }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={sens === "haut" ? "M3.5 10 L8 5.5 L12.5 10" : "M3.5 6 L8 10.5 L12.5 6"} />
    </svg>
  );
}

export function ReglagesTabs({ actif }: { actif: "checklists" | "parametres" | "integrations" | "offre" }) {
  return (
    <nav className="filtres" aria-label="Réglages">
      <a className="filtre" href="/admin/checklists" aria-current={actif === "checklists" ? "page" : undefined} style={{ textDecoration: "none" }}>Checklists</a>
      <a className="filtre" href="/admin/parametres" aria-current={actif === "parametres" ? "page" : undefined} style={{ textDecoration: "none" }}>Alertes et société</a>
      <a className="filtre" href="/admin/integrations" aria-current={actif === "integrations" ? "page" : undefined} style={{ textDecoration: "none" }}>Intégrations</a>
      <a className="filtre" href="/admin/offre" aria-current={actif === "offre" ? "page" : undefined} style={{ textDecoration: "none" }}>Mon offre</a>
    </nav>
  );
}

export function FlotteTabs({ actif }: { actif: "vehicules" | "conducteurs" | "depots" }) {
  return (
    <nav className="filtres" aria-label="Flotte">
      <a className="filtre" href="/admin/flotte" aria-current={actif === "vehicules" ? "page" : undefined} style={{ textDecoration: "none" }}>Véhicules</a>
      <a className="filtre" href="/admin/conducteurs" aria-current={actif === "conducteurs" ? "page" : undefined} style={{ textDecoration: "none" }}>Conducteurs</a>
      <a className="filtre" href="/admin/depots" aria-current={actif === "depots" ? "page" : undefined} style={{ textDecoration: "none" }}>Dépôts</a>
    </nav>
  );
}

export function CommandesTabs({ actif }: { actif: "commandes" | "itineraire" }) {
  return (
    <nav className="filtres" aria-label="Commandes">
      <a className="filtre" href="/admin/commandes" aria-current={actif === "commandes" ? "page" : undefined} style={{ textDecoration: "none" }}>Commandes du jour</a>
      <a className="filtre" href="/admin/itineraires" aria-current={actif === "itineraire" ? "page" : undefined} style={{ textDecoration: "none" }}>Itinéraire</a>
    </nav>
  );
}

export function BandeauPublic() {
  return (
    <header className="band">
      <div className="band-in"><Brand href="/" /></div>
    </header>
  );
}

export const dateHeure = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
