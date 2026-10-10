#!/bin/bash
set -euo pipefail

BACKUP_ROOT="/var/backups/caixaclaro"
DAILY="${BACKUP_ROOT}/daily"
WEEKLY="${BACKUP_ROOT}/weekly"
MONTHLY="${BACKUP_ROOT}/monthly"
PASS_FILE="/opt/caixaclaro/.backup-passphrase"
ENV_FILE="/opt/caixaclaro/backend/.env"
REPO_DIR="/opt/caixaclaro"
ROOT_ENV="${REPO_DIR}/.env"
IMAGE="caixaclaro-backup:1"
NETWORK="caixaclaro-prod_default"
DB_CONTAINER="caixaclaro-prod-db-1"
DB_HOST="db"
DB_PORT="5432"
DB_NAME="caixaclaro"
DB_USER="caixaclaro"
RETAIN_DAILY=7
RETAIN_WEEKLY=4
RETAIN_MONTHLY=3

log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
fail() { log "FAIL: $*" >&2; exit 1; }

[ -f "$PASS_FILE" ] || fail "passphrase ausente: $PASS_FILE"
perm=$(stat -c '%a' "$PASS_FILE")
owner=$(stat -c '%U:%G' "$PASS_FILE")
[ "$perm"  = "600"       ] || fail "permissão do passphrase != 600 (é $perm)"
[ "$owner" = "root:root" ] || fail "dono do passphrase != root:root (é $owner)"

PP=$(cat "$PASS_FILE")
[ -n "$PP" ] || fail "passphrase vazia"

[ -f "$ENV_FILE" ] || fail ".env do backend ausente: $ENV_FILE"
[ -f "$ROOT_ENV" ] || fail ".env raiz ausente: $ROOT_ENV"

docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || fail "imagem $IMAGE não existe (rodar: docker build -t $IMAGE $REPO_DIR/backup)"
docker network inspect "$NETWORK" >/dev/null 2>&1 \
  || fail "network $NETWORK não existe"
docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q '^true$' \
  || fail "container $DB_CONTAINER não está rodando"

PGPASSWORD_VALUE=$(grep '^POSTGRES_PASSWORD=' "$ROOT_ENV" | cut -d= -f2-)
[ -n "$PGPASSWORD_VALUE" ] || fail "POSTGRES_PASSWORD vazio em $ROOT_ENV"

GIT_COMMIT=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)

mkdir -p "$DAILY" "$WEEKLY" "$MONTHLY"
[ -w "$DAILY" ] || fail "sem permissão de escrita em $DAILY"

TS=$(date -u +%Y%m%dT%H%M%SZ)
NAME="caixaclaro-$TS"
log "iniciando backup $NAME"

if ! printf '%s\n' "$PP" | docker run --rm -i \
        --network "$NETWORK" \
        --tmpfs "/work:size=512m,mode=0700" \
        -v "$ENV_FILE:/secrets/.env:ro" \
        -v "$DAILY:/out" \
        -e "BACKUP_NAME=$NAME" \
        -e "GIT_COMMIT=$GIT_COMMIT" \
        -e "PGHOST=$DB_HOST" \
        -e "PGPORT=$DB_PORT" \
        -e "PGDATABASE=$DB_NAME" \
        -e "PGUSER=$DB_USER" \
        -e "PGPASSWORD=$PGPASSWORD_VALUE" \
        "$IMAGE"
then
  fail "container de backup retornou erro"
fi
unset PP PGPASSWORD_VALUE

OUT="${DAILY}/${NAME}.tar.gpg"
CHECK="${OUT}.sha256"
[ -f "$OUT"   ] || fail "artefato não criado: $OUT"
[ -s "$OUT"   ] || fail "artefato vazio: $OUT"
[ -f "$CHECK" ] || fail "sha256 não criado: $CHECK"

expected=$(awk '{print $1}' "$CHECK")
actual=$(sha256sum "$OUT" | awk '{print $1}')
[ "$expected" = "$actual" ] || fail "sha256 divergente"

log "OK  $OUT  ($(stat -c%s "$OUT") bytes)"

rotate() {
  local from="$1" to="$2" keep="$3"
  mapfile -t files < <(find "$from" -maxdepth 1 -name 'caixaclaro-*.tar.gpg' -printf '%f\n' | sort)
  while [ "${#files[@]}" -gt "$keep" ]; do
    local oldest="${files[0]}"
    if [ -n "$to" ]; then
      mv "$from/$oldest"            "$to/$oldest"
      mv "$from/$oldest.sha256"     "$to/$oldest.sha256" 2>/dev/null || true
    else
      rm -f "$from/$oldest" "$from/$oldest.sha256"
    fi
    files=("${files[@]:1}")
  done
}

rotate "$DAILY"   "$WEEKLY"  "$RETAIN_DAILY"
rotate "$WEEKLY"  "$MONTHLY" "$RETAIN_WEEKLY"
rotate "$MONTHLY" ""         "$RETAIN_MONTHLY"

log "rotação concluída"

# --- Upload remoto (R2) ----------------------------------------------
# Requer: /opt/caixaclaro/.rclone.conf (600 root:root) + remote caixaclaro-r2
# Falha aqui NAO apaga nem desfaz o backup local, que ja foi gravado e
# rotacionado acima. Mas o script termina com codigo 2: antes ele saia com
# 0, e o agendador registrava sucesso mesmo com a copia fora do VPS falhando
# todo dia (revisao de 2026-10-09, achado R13).
#   0 = backup local e copia no R2 ok
#   1 = backup local falhou (fail acima)
#   2 = backup local ok, copia no R2 falhou ou nao configurada
# A unidade do agendador nao deve usar Restart=on-failure: cada reinicio
# geraria mais um backup.
RCLONE_CONF="/opt/caixaclaro/.rclone.conf"
RCLONE_REMOTE="caixaclaro-r2:caixaclaro-backup"
EXIT_UPLOAD_FALHOU=2

if [ ! -f "$RCLONE_CONF" ]; then
  log "FAIL rclone config ausente ($RCLONE_CONF); copia no R2 NAO feita; backup local preservado" >&2
  exit "$EXIT_UPLOAD_FALHOU"
fi

if rclone --config "$RCLONE_CONF" copy "$BACKUP_ROOT" "$RCLONE_REMOTE" \
     --include "*.tar.gpg" \
     --include "*.tar.gpg.sha256" \
     --log-level ERROR \
     2>&1; then
  log "OK upload R2 ($RCLONE_REMOTE)"
else
  log "FAIL upload R2 falhou; backup local preservado" >&2
  exit "$EXIT_UPLOAD_FALHOU"
fi

exit 0
