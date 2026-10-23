# Routage poids lourd (Valhalla)

Flotta calcule les itinéraires avec [Valhalla](https://github.com/valhalla/valhalla), profil `truck`, à partir du gabarit de la fiche véhicule : hauteur, largeur, longueur, PTAC, nombre d'essieux, ADR (matières dangereuses). Valhalla évite les restrictions OpenStreetMap qui interdisent le passage (hauteur limitée, poids, etc.).

## Démarrer le service

```bash
docker compose --profile routage up -d valhalla
docker compose logs -f valhalla
```

Au premier démarrage, le conteneur télécharge la carte de France (Geofabrik, environ 4,5 Go) dans `valhalla/custom_files/` puis construit les tuiles : prévoir 1 à 2 heures, 16 Go de RAM conseillés et une vingtaine de Go de disque. Tant que les tuiles ne sont pas prêtes, les écrans affichent « service indisponible » : aucun itinéraire n'est jamais inventé.

L'API joint Valhalla par `VALHALLA_URL` (défaut `http://valhalla:8002`).

## Mise à jour mensuelle de la carte

```bash
./scripts/valhalla-maj.sh
```

Le script retélécharge la carte France et reconstruit les tuiles (`VALHALLA_FORCE_REBUILD=True`). Pendant la reconstruction, le service est indisponible : lancer de préférence la nuit. Exemple de cron : `0 3 1 * * /chemin/vers/flotta/scripts/valhalla-maj.sh`.

## Estimation des coûts

Chaque itinéraire renvoie une **estimation** (jamais une valeur contractuelle) calculée avec les hypothèses de la société (Réglages) : consommation (l/100 km), prix du carburant, coût kilométrique d'exploitation et coût du péage au kilomètre, appliqué à toute la distance si l'itinéraire emprunte un péage. Valhalla ne fournit pas de tarif de péage : aucune API payante n'est utilisée.

## Valider un cas réel

Le dossier `api/tests/data/` explique comment ajouter un cas réel (pont bas) pour vérifier qu'un camion trop haut ne passe pas sous le pont.
