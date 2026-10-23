import GrilleOffres from "./GrilleOffres";
import { Brand } from "./ui";

export default function Accueil() {
  return (
    <div className="landing">
      <header className="band">
        <div className="band-in">
          <Brand href="/" />
          <nav className="nav" aria-label="Sections"><a href="#controle">Contrôle départ</a><a href="#tournees">Tournées</a><a href="#tarifs">Tarifs</a></nav>
          <div className="who"><a className="btn btn-sm" href="/connexion">Espace exploitant</a></div>
        </div>
      </header>
      <main>
        <section className="hero">
          <h1>Des camions contrôlés avant de partir. Des tournées plus courtes.</h1>
          <p className="hero-sous">Flotta est l'outil des exploitants de PME de transport : le contrôle avant départ sur téléphone, et la planification des tournées poids lourd qui respecte les temps de conduite légaux.</p>
          <div className="hero-actions">
            <a className="btn btn-primary" href="#tarifs">Voir les tarifs</a>
            <a className="btn" href="/c/demo">Essayer le contrôle chauffeur</a>
          </div>
        </section>

        <section className="bloc" id="controle">
          <div className="bloc-titre">
            <p className="bloc-sur">Contrôle avant départ</p>
            <h2>Le chauffeur scanne, répond, repart. Vous savez quels camions peuvent partir.</h2>
          </div>
          <ol className="pas">
            <li><strong>Un QR code dans la cabine.</strong> Pas d'application ni de mot de passe : le chauffeur ouvre la page sur son téléphone, y compris sans réseau.</li>
            <li><strong>Un point par écran, gros boutons.</strong> Pensé pour être utilisable debout, dehors, avec des gants. Photos et signature si besoin.</li>
            <li><strong>Défaut critique : le camion est bloqué et vous êtes prévenu par email.</strong> Vous le débloquez avec un commentaire, tout est tracé.</li>
            <li><strong>Tableau du jour.</strong> Contrôlé, non contrôlé, défaut, bloqué : l'état de la flotte se lit en quelques secondes, avec un PDF par contrôle.</li>
          </ol>
        </section>

        <section className="bloc" id="tournees">
          <div className="bloc-titre">
            <p className="bloc-sur">Tournées poids lourd</p>
            <h2>Importez vos commandes, obtenez des tournées réalistes pour vos camions.</h2>
          </div>
          <ol className="pas">
            <li><strong>Import Excel ou CSV</strong>, adresses localisées automatiquement, corrigibles sur la carte.</li>
            <li><strong>Itinéraires calculés pour le gabarit de chaque camion</strong> (hauteur, poids, essieux), avec fenêtres horaires, capacités, frigo et ADR.</li>
            <li><strong>Temps de conduite et pauses du règlement CE 561/2006</strong> intégrés au calcul, avec alerte si une modification à la main crée une infraction.</li>
            <li><strong>Plan envoyé sur le téléphone du chauffeur</strong>, statuts et preuves de livraison, suivi en direct pour vous.</li>
            <li><strong>Quand la journée déraille</strong> : retards prévus, solutions chiffrées pour une commande urgente ou une panne. Rien ne change sans votre validation.</li>
          </ol>
        </section>

        <section className="bloc" id="tarifs">
          <div className="bloc-titre">
            <p className="bloc-sur">Tarifs</p>
            <h2>Un prix par camion, sans engagement de modules.</h2>
          </div>
          <GrilleOffres action={<div className="hero-actions" style={{ marginTop: 24 }}><a className="btn btn-primary" href="/connexion">Espace exploitant</a></div>} />
        </section>
      </main>
      <footer className="pied">
        <Brand />
        <p className="hint">Flotta, logiciel pour entreprises de transport routier de marchandises. Les données personnelles (conducteurs, positions) sont traitées selon le RGPD, avec une durée de conservation réglable.</p>
      </footer>
    </div>
  );
}
