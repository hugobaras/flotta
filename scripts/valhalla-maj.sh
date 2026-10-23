#!/bin/sh
# Mise à jour mensuelle des tuiles de routage : retélécharge la carte France et reconstruit les tuiles.
# À lancer depuis la racine du projet (cron mensuel conseillé : 0 3 1 * * /chemin/scripts/valhalla-maj.sh).
set -eu
cd "$(dirname "$0")/.."
rm -f valhalla/custom_files/france-latest.osm.pbf
VALHALLA_FORCE_REBUILD=True docker compose --profile routage up -d --force-recreate valhalla
echo "Reconstruction lancée : suivez-la avec « docker compose logs -f valhalla ». Le service répond de nouveau quand elle est terminée."
