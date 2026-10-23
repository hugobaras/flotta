import { Brand } from "./ui";

export default function Home() {
  return (
    <main className="center-page">
      <div className="auth-card">
        <Brand />
        <div className="panel">
          <div className="panel-body">
            <h1>Contrôle avant départ</h1>
            <p className="muted">Chauffeur : scannez le QR code collé dans votre cabine pour démarrer le contrôle de votre camion.</p>
            <a className="btn btn-primary" href="/connexion">Espace exploitant</a>
            <a className="btn" href="/c/demo">Voir le camion de démonstration</a>
          </div>
        </div>
      </div>
    </main>
  );
}
