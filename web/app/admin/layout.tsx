export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <a href="/admin">Tableau de bord</a>
        <a href="/admin/controles">Contrôles</a>
        <a href="/admin/checklists">Checklists</a>
        <a href="/admin/parametres">Paramètres</a>
      </nav>
      {children}
    </>
  );
}
