#!/bin/bash
# Lance la sauvegarde chaque jour à HEURE_SAUVEGARDE (heure du conteneur, UTC).
while true; do
  cible=$(date -d "today ${HEURE_SAUVEGARDE:-02:30}" +%s)
  now=$(date +%s)
  [ "$cible" -le "$now" ] && cible=$(date -d "tomorrow ${HEURE_SAUVEGARDE:-02:30}" +%s)
  sleep $((cible - now))
  sauvegarde.sh || echo "ECHEC SAUVEGARDE $(date -Is)"
done
