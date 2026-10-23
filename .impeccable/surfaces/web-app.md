---
version: 1
slug: "web-app"
primary_target: "web/app"
related_targets: []
---

# Surface brief : application Flotta (exploitant et chauffeur)

Mode : Operate. Audience : exploitants au bureau (ordinateur), chauffeurs en cabine (téléphone, plein jour). Action : voir quels camions peuvent partir, débloquer, relire un contrôle ; remplir un contrôle en moins de deux minutes.

## Direction contract

THESIS: un outil de travail calme, contemporain et précis : la typographie et l'espace font le design, pas des composants empilés. Refuse la coque SaaS (barre latérale, panneaux blancs arrondis, badges, icônes partout) et la skeuomorphie (plaque, vignette) jugée datée.
OWN-WORLD: fond blanc cassé chaud #fafaf9, encre #111418, filets #e7e5e4, accent unique orange signal #e5560a (marque et soulignement actif, jamais sur du texte courant), états vert/ambre/rouge en point + texte. Geist (variable) et Geist Mono pour plaques et valeurs, tracking serré sur les titres. Boutons noirs pleins, coins 6 px, aucune ombre hors dialogue.
STORY: l'exploitant lit la flotte comme une liste aérée et voit en un coup d'œil ce qui roule et ce qui est bloqué ; le chauffeur coche de grandes lignes simples et termine sur un écran clair.
FIRST VIEWPORT: navigation en haut en texte seul (marque, quatre liens, compte), grand titre léger, filtres d'état en texte avec compteurs, liste de lignes séparées par des filets (plaque mono, point d'état + texte, dernier contrôle, action). Chauffeur : marque, plaque, titre, lignes de points pleine largeur avec OK / Défaut, barre de validation fixe.
FORM: canon contemporain, user-pinned ("moderne et sobre"), seed key e8f78bfc non appliquée.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
