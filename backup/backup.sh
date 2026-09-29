#!/bin/bash
set -euo pipefail

: "${BACKUP_NAME:?BACKUP_NAME ausente}"
: "${PGHOST:?PGHOST ausente}"
: "${PGDATABASE:?PGDATABASE ausente}"
: "${PGUSER:?PGUSER ausente}"
: "${ENV_FILE:=/secrets/.env}"
: "${WORK_DIR:=/work}"
: "${OUTPUT_DIR:=/out}"
: "${GIT_COMMIT:=unknown}"

CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PKG_DIR="${WORK_DIR}/caixaclaro"

cleanup() {
  rm -rf "${PKG_DIR}" "${WORK_DIR}/.pass" "${WORK_DIR}/verify"
}
trap cleanup EXIT

mkdir -p "${PKG_DIR}/env" "${OUTPUT_DIR}" "${WORK_DIR}/verify"

IFS= read -r PASSPHRASE
if [ -z "${PASSPHRASE}" ]; then
  echo "ERRO: passphrase vazia" >&2
  exit 2
fi
printf '%s' "${PASSPHRASE}" > "${WORK_DIR}/.pass"
chmod 600 "${WORK_DIR}/.pass"
unset PASSPHRASE

pg_dump -Fc -f "${PKG_DIR}/db.dump"
DUMP_SIZE="$(stat -c%s "${PKG_DIR}/db.dump")"
DUMP_SHA="$(sha256sum "${PKG_DIR}/db.dump" | awk '{print $1}')"

install -m 600 "${ENV_FILE}" "${PKG_DIR}/env/.env"
ENV_SHA="$(sha256sum "${PKG_DIR}/env/.env" | awk '{print $1}')"
KEYS_PRESENT="$(grep -E '^[A-Z_][A-Z0-9_]*=' "${PKG_DIR}/env/.env" | cut -d= -f1 | sort -u | jq -R . | jq -sc .)"

cat > "${PKG_DIR}/MANIFEST.json" <<JSON
{
  "schema_version": 1,
  "created_at": "${CREATED_AT}",
  "created_by": "backup.sh v1",
  "host": "$(hostname)",
  "db": {
    "name": "${PGDATABASE}",
    "postgres_version": "$(pg_dump --version | awk '{print $3}')",
    "dump_format": "custom",
    "dump_size_bytes": ${DUMP_SIZE},
    "dump_sha256": "${DUMP_SHA}"
  },
  "env": {
    "included": true,
    "sha256": "${ENV_SHA}",
    "keys_present": ${KEYS_PRESENT}
  },
  "git": {
    "commit": "${GIT_COMMIT}",
    "dirty": false
  },
  "retention_tier": "daily"
}
JSON

OUT="${OUTPUT_DIR}/${BACKUP_NAME}.tar.gpg"
tar -C "${WORK_DIR}" -cf - caixaclaro | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-file "${WORK_DIR}/.pass" --symmetric --cipher-algo AES256 --compress-algo none -o "${OUT}"

( cd "${OUTPUT_DIR}" && sha256sum "${BACKUP_NAME}.tar.gpg" > "${BACKUP_NAME}.tar.gpg.sha256" )

gpg --batch --quiet --pinentry-mode loopback --passphrase-file "${WORK_DIR}/.pass" -d "${OUT}" | tar -tzf - | grep -qx "caixaclaro/MANIFEST.json"

gpg --batch --quiet --pinentry-mode loopback --passphrase-file "${WORK_DIR}/.pass" -d "${OUT}" | tar -xzf - -C "${WORK_DIR}/verify" caixaclaro/db.dump

pg_restore -l "${WORK_DIR}/verify/caixaclaro/db.dump" > /dev/null

echo "OK ${OUT}"
