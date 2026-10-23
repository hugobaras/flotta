# Registre des traitements (modèle à compléter et à faire relire par un juriste)

Responsable de traitement : l'entreprise cliente. Sous-traitant : l'éditeur de Flotta (voir `contrat-sous-traitance.md`).

| Traitement | Finalité | Données | Personnes | Base légale | Durée de conservation | Destinataires |
|---|---|---|---|---|---|---|
| Contrôle avant départ | Sécurité du parc, traçabilité des défauts | Nom du conducteur, réponses, photos, signature, position GPS | Conducteurs | Intérêt légitime, obligation de sécurité | 3 ans par défaut, réglable (Réglages), purge automatique | Exploitants de la société |
| Plans et suivi de livraison | Exécution des tournées | Nom et téléphone de contact destinataire, adresse, positions, signature et photo de preuve | Destinataires, conducteurs | Exécution du contrat de transport | Durée de conservation de la société, purge automatique | Exploitants |
| Temps de conduite | Respect du règlement CE 561/2006 | Activités déclarées (type, début, fin) | Conducteurs | Obligation légale | Durée de conservation de la société | Exploitants |
| Comptes exploitants | Accès à l'outil | Email, mot de passe haché (argon2) | Exploitants | Exécution du contrat | Durée du contrat | Équipe Flotta (support) |
| Journal d'audit | Sécurité, preuve des actions sensibles | Email de l'auteur, action | Exploitants | Intérêt légitime | Non purgé : à fixer avec le client | Administrateurs |

Mesures : HTTPS, mots de passe hachés, jetons de session hachés, isolation par société testée, codes PIN stockés sous forme d'empreinte, clés API hachées, journal d'audit, sauvegardes (`docs/exploitation.md`).
Droits des conducteurs : export (`GET /api/admin/conducteurs/{id}/export`) et effacement (`DELETE /api/admin/conducteurs/{id}/donnees`) par un administrateur ; les contrôles sont conservés mais anonymisés (nom, signature, position et photos supprimés).
Sous-traitants ultérieurs à lister avant mise en production : hébergeur (Scaleway ou OVH), Brevo (emails), Sentry (si activé), service d'adresses publiques api-adresse.data.gouv.fr (reçoit les adresses de livraison).
