#!/bin/sh
# Kronos launchd 서비스 설치.
#  - com.kronos.runner: 스케줄러 (KeepAlive)
#  - com.kronos.backup: 일일 03:00 DB 백업
#
# 사용: scripts/install-launchd.sh
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TEMPLATE_DIR="$PROJECT_DIR/scripts/launchd"

UV_BIN=$(command -v uv || true)
if [ -z "$UV_BIN" ]; then
  echo "uv 명령을 찾을 수 없습니다. PATH 또는 brew install uv를 확인해 주세요." >&2
  exit 1
fi

# launchd가 사용할 PATH (사용자 zsh PATH의 핵심)
LD_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$LAUNCH_AGENTS_DIR" "$PROJECT_DIR/logs" "$PROJECT_DIR/data/backups"
chmod +x "$PROJECT_DIR/scripts/backup.sh"

render() {
  local template="$1"
  local target="$2"
  sed \
    -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__UV_BIN__|$UV_BIN|g" \
    -e "s|__PATH__|$LD_PATH|g" \
    "$template" > "$target"
}

for label in com.kronos.runner com.kronos.backup; do
  template="$TEMPLATE_DIR/$label.plist.template"
  target="$LAUNCH_AGENTS_DIR/$label.plist"
  render "$template" "$target"
  echo "rendered: $target"
  # 기존 등록이 있으면 bootout 후 재등록
  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID" "$target"
  echo "loaded: $label"
done

echo ""
echo "상태 확인:"
echo "  launchctl print gui/$UID/com.kronos.runner | head -20"
echo "  launchctl print gui/$UID/com.kronos.backup | head -20"
echo "  tail -f $PROJECT_DIR/logs/scheduler.log"
