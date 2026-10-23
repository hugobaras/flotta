#!/bin/bash
# Restaure une sauvegarde : restauration.sh db-AAAAMMJJ-HHMMSS.dump [fichiers-AAAAMMJJ-HHMMSS.tar.gz]
# Les fichiers sont lus dans DOSSIER_SAUVEGARDES (ou téléchargés de S3 avec RECUPERER_S3=1). PGDATABASE peut cibler une base vide.
set -euo pipefail
dossier=${DOSSIER_SAUVEGARDES:-/backups}
if [ "${RECUPERER_S3:-}" = "1" ]; then
  opt=(); [ -n "${S3_ENDPOINT:-}" ] && opt=(--endpoint-url "$S3_ENDPOINT")
  for f in "$@"; do aws "${opt[@]}" s3 cp "s3://$S3_BUCKET/$f" "$dossier/$f"; done
fi
pg_restore --clean --if-exists --no-owner -d "$PGDATABASE" "$dossier/$1"
if [ -n "${2:-}" ]; then
  tar -xzf "$dossier/$2" -C "$(dirname "${UPLOAD_DIR:-/data/uploads}")"
fi
echo "Restauration terminée"
