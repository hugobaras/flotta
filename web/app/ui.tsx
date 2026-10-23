import { CircleCheck, Clock, OctagonAlert, TriangleAlert, Truck } from "lucide-react";

export type Statut = "controle" | "non_controle" | "defaut" | "bloque";

const STATUTS = {
  controle: { label: "Contrôlé", cls: "badge-ok", Icon: CircleCheck },
  non_controle: { label: "Non contrôlé", cls: "", Icon: Clock },
  defaut: { label: "Défaut", cls: "badge-warn", Icon: TriangleAlert },
  bloque: { label: "Bloqué", cls: "badge-danger", Icon: OctagonAlert },
} as const;

export const STATUT_LABELS: Record<Statut, string> = {
  controle: "Contrôlé", non_controle: "Non contrôlé", defaut: "Défaut", bloque: "Bloqué",
};

// Jamais la couleur seule : chaque état porte aussi une icône et un texte.
export function StatusBadge({ statut }: { statut: Statut }) {
  const { label, cls, Icon } = STATUTS[statut];
  return <span className={`badge ${cls}`}><Icon aria-hidden />{label}</span>;
}

export function Plaque({ children }: { children: React.ReactNode }) {
  return <span className="plaque">{children}</span>;
}

export function Brand({ href }: { href?: string }) {
  const content = (
    <>
      <span className="brand-mark"><Truck aria-hidden /></span>
      <span>Flotta</span>
    </>
  );
  return href ? <a className="brand" href={href}>{content}</a> : <div className="brand">{content}</div>;
}

export function Empty({ icon, title, children }: { icon: React.ReactNode; title: string; children?: React.ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export const dateHeure = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });

export const heure = (iso: string) => new Date(iso).toLocaleTimeString("fr-FR", { timeStyle: "short" });
