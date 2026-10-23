import { BandeauPublic } from "./ui";

export default function Home() {
  return (
    <div className="public">
      <BandeauPublic />
      <main className="public-body">
        <div className="auth">
          <div className="stack">
            <h1>Contrôle avant départ</h1>
            <p className="muted" style={{ marginTop: 8 }}>Chauffeur : scannez le QR code collé dans votre cabine pour contrôler votre camion.</p>
          </div>
          <div style={{ display: "grid", gap: 12 }}>
            <a className="btn btn-primary" href="/connexion">Espace exploitant</a>
            <a className="btn" href="/c/demo">Camion de démonstration</a>
          </div>
        </div>
      </main>
    </div>
  );
}
