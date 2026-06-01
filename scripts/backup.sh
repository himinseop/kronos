#!/bin/sh
# Kronos SQLite 일일 백업. launchd com.kronos.backup이 매일 03:00 KST에 실행.
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="$PROJECT_DIR/data/kronos.db"
BACKUP_DIR="$PROJECT_DIR/data/backups"

if [ ! -f "$DB_PATH" ]; then
  echo "[$(date)] DB 없음: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

TS=$(date +%Y%m%d-%H%M%S)
TMP_BACKUP="$BACKUP_DIR/kronos-$TS.db"

# sqlite3 .backup은 라이브 DB에서도 안전하게 일관 스냅샷
sqlite3 "$DB_PATH" ".backup '$TMP_BACKUP'"
gzip -9 "$TMP_BACKUP"

# 30일 이상 된 백업 제거
find "$BACKUP_DIR" -name 'kronos-*.db.gz' -mtime +30 -delete

SIZE=$(stat -f '%z' "$TMP_BACKUP.gz" 2>/dev/null || echo 0)
echo "[$(date)] backup ok: $TMP_BACKUP.gz ($SIZE bytes)"
