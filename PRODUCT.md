# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Exploitants** (responsables d'exploitation, dispatchers) de PME de transport routier de marchandises, 10 à 50 poids lourds, France. Ils travaillent au bureau sur ordinateur : ils suivent l'état de la flotte du jour, débloquent un camion, relisent des contrôles, règlent les checklists.
- **Chauffeurs** : ils scannent le QR code collé dans la cabine et remplissent le contrôle avant départ sur leur téléphone, souvent debout, dehors, parfois avec des gants. Pas de compte ni de mot de passe : le jeton du QR fait foi.

## Product Purpose

Flotta est un SaaS B2B pour entreprises de transport routier. Premier module : le contrôle avant départ sur téléphone (checklist, photos, signature, position), avec blocage du camion et alerte par email sur défaut critique. Second module à venir : routage poids lourd et optimisation de tournées avec respect des temps de conduite légaux (CE 561/2006). Succès : le chauffeur termine son contrôle en moins de deux minutes, l'exploitant sait en un coup d'œil quels camions peuvent partir.

## Operating Context

Interface entièrement en français. Les exploitants consultent des listes, filtrent par jour, véhicule, conducteur, et téléchargent des PDF de contrôle. Les chauffeurs utilisent le site web mobile (pas d'application native), en plein jour comme en cabine.

## Capabilities and Constraints

Site web uniquement (Next.js, app router, TypeScript). Pas d'application native. Les pages chauffeur fonctionnent sans compte. Données personnelles (noms, signatures, positions) soumises au RGPD. Identité visuelle non encore définie : aucun logo ni couleur imposés.

## Brand Commitments

Nom du produit affiché : **Flotta**. Aucune autre contrainte d'identité (confirmé par l'utilisateur).

Direction visuelle choisie par l'utilisateur : **sobre et neutre**, le standard des SaaS B2B bien faits (fond clair, gris ardoise, un seul accent indigo, états vert/ambre/rouge). Niveau de finition visé : Linear, Stripe Dashboard, Samsara (repères supposés, non confirmés). Pas de mode sombre : usage au bureau et en plein jour.

## Evidence on Hand

Aucun logo, aucune charte, aucun témoignage ni client réel. Ne pas inventer de références clients ni de chiffres.

## Product Principles

- Lisibilité d'abord : l'état de la flotte se lit en quelques secondes.
- Le chauffeur n'a jamais à réfléchir : grandes cibles tactiles, un seul geste par point.
- Un défaut critique est toujours visible et jamais ambigu.
- Sobre et fiable : un outil de travail, pas une vitrine.

## Accessibility & Inclusion

Cibles tactiles larges pour les chauffeurs (gants, mobilité). Contraste suffisant en plein soleil. Les statuts ne reposent jamais sur la couleur seule.
