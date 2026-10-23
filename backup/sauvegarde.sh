#!/bin/bash
# Sauvegarde la base (pg_dump) et les fichiers envoyés ; copie vers S3 si S3_BUCKET est défini ; garde 7 jours en local.
set -euo pipefail
dossier=${DOSSIER_SAUVEGARDES:-/backups}
uploads=${UPLOAD_DIR:-/data/uploads}
d=$(date +%Y%m%d-%H%M%S)
pg_dump -Fc --no-owner -f "$dossier/db-$d.dump"
tar -czf "$dossier/fichiers-$d.tar.gz" -C "$(dirname "$uploads")" "$(basename "$uploads")"
if [ -n "${S3_BUCKET:-}" ]; then
  opt=(); [ -n "${S3_ENDPOINT:-}" ] && opt=(--endpoint-url "$S3_ENDPOINT")
  aws "${opt[@]}" s3 cp "$dossier/db-$d.dump" "s3://$S3_BUCKET/db-$d.dump"
  aws "${opt[@]}" s3 cp "$dossier/fichiers-$d.tar.gz" "s3://$S3_BUCKET/fichiers-$d.tar.gz"
fi
find "$dossier" -name 'db-*.dump' -mtime +7 -delete
find "$dossier" -name 'fichiers-*.tar.gz' -mtime +7 -delete
echo "Sauvegarde $d terminée"
