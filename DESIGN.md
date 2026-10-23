---
name: Flotta
description: "Encre & signal : un outil de travail calme, typographique, sur fond blanc cassé chaud, avec un seul accent orange."
colors:
  paper: "#fafaf9"
  white: "#ffffff"
  ink: "#111418"
  ink-2: "#44484f"
  ink-3: "#686d76"
  hairline: "#e7e5e4"
  hairline-strong: "#d3d0cd"
  signal: "#e5560a"
  state-ok: "#1a7f4b"
  state-warn: "#c77700"
  state-danger: "#d3281b"
  state-idle: "#9a9fa8"
  notice-tint: "#fff4e8"
  notice-line: "#f3cfa6"
  danger-tint: "#fef1ef"
typography:
  display:
    fontFamily: "Geist Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "34px"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Geist Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Geist Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Geist Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "-0.006em"
  label:
    fontFamily: "Geist Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.4
  plate:
    fontFamily: "Geist Mono Variable, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "13.5px"
    fontWeight: 500
    letterSpacing: "0.02em"
rounded:
  sm: "5px"
  md: "6px"
  lg: "8px"
  field-mobile: "10px"
  dialog: "14px"
spacing:
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "40px"
  xl: "56px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "#2a2f36"
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "36px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
  button-danger:
    backgroundColor: "{colors.state-danger}"
    textColor: "{colors.white}"
    rounded: "{rounded.md}"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "38px"
  plate:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    typography: "{typography.plate}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  notice:
    backgroundColor: "{colors.notice-tint}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "12px 16px"
---

# Design System: Flotta

## Overview

**Creative North Star: "Encre & signal"**

Un outil de travail calme et précis : la typographie, l'espace et des filets fins font le design, pas des composants empilés. Le fond est un blanc cassé chaud, l'encre quasi noire, et un unique orange signal marque l'identité. Les états se lisent par un point coloré et un mot, jamais par un badge. La page est ouverte : pas de panneaux blancs encadrés, des lignes séparées par des filets, de grands titres légers au tracking serré.

Deux registres partagent le même vocabulaire. Côté exploitant (ordinateur) : bandeau supérieur en texte seul, colonne de 1120px, listes aérées. Côté chauffeur (téléphone, plein jour, parfois avec des gants) : même encre et mêmes filets, mais cibles de 52 à 56px, texte de 17px, une barre de validation fixe en bas.

**Key Characteristics:**
- Fond blanc cassé chaud, encre quasi noire, aucun mode sombre.
- Un seul accent (orange signal), réservé à la marque et au soulignement de navigation active.
- États vert / ambre / rouge en point de 8px + texte.
- Boutons primaires noirs pleins, coins de 6px, pas d'ombre hors dialogue.
- Geist Variable pour le texte, Geist Mono pour plaques et valeurs.
- Listes à filets, sans cadres ni cartes.

## Colors

Palette neutre chaude, un accent, trois couleurs d'état utilitaires.

### Primary
- **Encre** (`ink`): texte, boutons primaires, contour de focus, soulignement des filtres actifs, cases cochées.
- **Orange signal** (`signal`): losange de marque et soulignement de la page active dans la navigation. Rien d'autre.

### Neutral
- **Papier chaud** (`paper`): fond de page, barre de validation chauffeur (à 92% d'opacité).
- **Blanc** (`white`): champs, boutons secondaires, plaques, survol de ligne, dialogue.
- **Encre 2** (`ink-2`): texte secondaire, boutons fantômes.
- **Encre 3** (`ink-3`): légendes, indices, en-têtes de colonnes, liens de navigation au repos.
- **Filet** (`hairline`): séparateurs de lignes et du bandeau. **Filet fort** (`hairline-strong`): contours de champs et boutons.

### States
- **Vert** (`state-ok`): contrôlé. **Ambre** (`state-warn`): défaut. **Rouge** (`state-danger`): bloqué, erreur, bouton destructif. **Gris** (`state-idle`): non contrôlé (anneau vide).
- **Teinte d'avis** (`notice-tint`, `notice-line`) et **teinte de danger** (`danger-tint`): fonds des avis.

### Named Rules
**The One Signal Rule.** L'orange n'apparaît que sur le losange de marque et le soulignement actif de la navigation. Jamais sur du texte, un bouton ou un état.
**The Dot And Word Rule.** Un état n'est jamais porté par la couleur seule : point de 8px plus libellé ("Contrôlé", "Défaut", "Bloqué", "Non contrôlé").

## Typography

**Display / Body Font:** Geist Variable (repli ui-sans-serif, system-ui)
**Label/Mono Font:** Geist Mono Variable (repli ui-monospace, SF Mono, Menlo)

**Character:** Un sans géométrique neutre, léger sur les grands titres, avec un tracking négatif qui lui donne du poids sans graisse. La mono n'apparaît que pour ce qui se lit comme une donnée : plaques d'immatriculation.

### Hierarchy
- **Display** (500, 34px, 1.1, -0.03em): titre de page; 28px sous 760px; 30px côté chauffeur; 36px sur l'écran de résultat.
- **Headline** (600, 20px, -0.02em): titre de dialogue; 18px pour les sections chauffeur.
- **Title** (600, 16px, 1.3): titres de section (h2) sous filet.
- **Body** (400, 15px, 1.5): texte courant; 17px côté chauffeur. Chiffres tabulaires pour tableaux et compteurs.
- **Label** (400, 13.5px à 14px): en-têtes de colonnes, indices, légendes en `ink-3`. Pas de capitales, pas d'espacement élargi.
- **Plate** (Geist Mono 500, 13.5px, +0.02em): plaque d'immatriculation; 26px en grande plaque d'en-tête chauffeur.

### Named Rules
**The Tight Heading Rule.** Les titres ont un tracking négatif (-0.01em à -0.03em) et un poids 500 à 600, jamais plus.

## Layout

Colonne unique centrée de 1120px max, marges de 32px (16px sous 760px), padding vertical de 56px en haut. Les titres de page se placent en tête avec une action alignée à droite; sections espacées de 48px, titres de section sur un filet. Les listes sont des tableaux sans cadre: lignes de 16px de padding vertical, séparées par un filet, en-têtes `ink-3`. Sous 640px les lignes passent en piles flex ("rack-cards"). Les paramètres sont en deux colonnes (280px + reste, espace de 48px) qui s'empilent sous 760px. Le détail d'un contrôle est en 1.5fr / 1fr avec 64px d'espace, empilé sous 960px. Côté chauffeur : colonne de 600px, lignes de points pleine largeur, boutons OK / Défaut en deux colonnes de 54px de haut, barre de validation fixe en bas avec zone sûre.

L'échelle d'espacement observée est 4, 8, 12, 16, 24, 32, 40, 48, 56.

## Elevation & Depth

Plat par défaut. La profondeur vient des filets et d'un survol de ligne qui passe au blanc (débordant de 16px de chaque côté grâce à une ombre pleine sans flou). La seule ombre est celle du dialogue, qui flotte au-dessus d'un voile de 35% d'encre avec un flou de 2px. Le champ en focus reçoit un halo de 3px à 12% d'encre.

### Shadow Vocabulary
- **Dialogue** (`box-shadow: 0 24px 60px rgba(17,20,24,0.2), 0 2px 8px rgba(17,20,24,0.08)`): dialogues uniquement.
- **Halo de focus de champ** (`box-shadow: 0 0 0 3px rgba(17,20,24,0.12)`): champs en focus.

### Named Rules
**The Flat-By-Default Rule.** Aucune ombre sur les boutons, listes, avis ou barres. Seul le dialogue en porte une.

## Shapes

Coins de 6px sur boutons et champs, 5px sur plaques et cases à cocher, 8px sur avis et miniatures, 14px sur dialogue. Côté chauffeur les cibles tactiles montent à 10px (champs, OK / Défaut, signature) et 12px (bouton de validation). Les filets sont de 1px; les soulignements actifs de 2px. Le point d'état est un cercle de 8px; l'état "non contrôlé" est un anneau vide de 1.5px. Le losange de marque est un carré de 12px à coins de 3px tourné de 45 degrés.

## Components

### Buttons
- **Shape:** coins de 6px, hauteur 36px (30px en petit, 56px en pleine largeur chauffeur).
- **Primary:** encre pleine, texte blanc, padding 0 14px. Survol `#2a2f36`.
- **Secondary:** fond blanc, filet fort; le survol assombrit le contour en encre.
- **Ghost:** transparent, texte `ink-2`; fond gris chaud au survol.
- **Danger:** rouge plein, pour les actions destructives et le "Défaut" sélectionné.
- **Disabled:** opacité 0.4. Transition de 150ms, courbe `cubic-bezier(0.22,1,0.36,1)`.

### Inputs / Fields
- **Style:** fond blanc, filet fort, coins de 6px, hauteur 38px; 52px et 17px côté chauffeur.
- **Focus:** contour encre plus halo de 3px; erreur en `state-danger` avec message en texte.
- **Case à cocher:** 18px, coins de 5px, coche blanche sur encre.

### Navigation
Bandeau supérieur de 64px en texte seul: marque à gauche, quatre liens (Tableau de bord, Contrôles, Checklists, Paramètres) en `ink-3` 500, compte et "Déconnexion" fantôme à droite. Page active: texte encre avec soulignement orange de 2px. Sous 760px le bandeau se replie, les liens défilent horizontalement avec des cibles de 44px.

### Filtres d'état
Texte en ligne sur un filet avec compteurs tabulaires; actif en encre avec soulignement d'encre de 2px.

### Listes à filets
Tableau sans cadre: en-têtes en `ink-3`, lignes séparées par un filet, premier lien en 500, survol blanc. État vide centré avec titre de 18px.

### Plaque et état
Plaque: Geist Mono dans un filet fort sur blanc, coins de 5px, pas d'imitation de plaque réelle. État: point de 8px et libellé en 500.

### Avis
Fond teinté, filet teinté, coins de 8px, padding 12px 16px; variantes danger et ok.

### Dialogue
480px max, blanc, coins de 14px, ombre propre, entrée en 220ms (légère montée et échelle), actions alignées à droite.

### Contrôle chauffeur
Lignes de points sous filet; choix OK (encre) / Défaut (rouge) en deux boutons de 54px; zone de dépôt de photo en pointillé; signature sur toile blanche de 170px; barre de validation fixe translucide; écran de résultat avec grand signe cerclé (vert ou rouge) animé en 500ms.

## Do's and Don'ts

### Do:
- **Do** garder l'orange `#e5560a` pour le losange de marque et le soulignement actif seulement.
- **Do** coupler tout état à un point et à un mot.
- **Do** séparer les contenus par des filets de 1px (`hairline`) plutôt que par des cadres.
- **Do** mettre plaques et valeurs en Geist Mono, le reste en Geist.
- **Do** utiliser des boutons primaires noirs, coins de 6px, sans ombre.
- **Do** respecter `prefers-reduced-motion` et un focus visible de 2px en encre.

### Don't:
- **Don't** ajouter une barre latérale, des cartes blanches arrondies, des badges ou des icônes décoratives.
- **Don't** introduire une teinte d'accent supplémentaire (indigo, bleu) ni un mode sombre.
- **Don't** imiter une vraie plaque d'immatriculation ni un macaron.
- **Don't** ajouter une ombre hors dialogue.
- **Don't** utiliser de capitales espacées ni de petits textes de surtitre.
