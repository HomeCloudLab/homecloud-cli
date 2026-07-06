#!/usr/bin/env bash
set -euo pipefail
bash -n /mnt/c/projects/HOMELAB_MINI_AWS_CONSOLE/homecloud-cli/install/install.sh
echo "syntax_ok"

SERVE=/tmp/hc-install-test
rm -rf "$SERVE" /tmp/hc-cli-bin
mkdir -p "$SERVE/releases/latest" /tmp/hc-cli-bin
cat > "$SERVE/releases/latest/homecloud-linux-amd64" <<'EOF'
#!/bin/sh
echo "homecloud 0.2.0 (linux-amd64, standalone)"
EOF
chmod +x "$SERVE/releases/latest/homecloud-linux-amd64"

cd "$SERVE"
python3 -m http.server 18766 --bind 127.0.0.1 >/dev/null 2>&1 &
PID=$!
sleep 1

HOMECLOUD_INSTALL_URL=http://127.0.0.1:18766/releases \
HOMECLOUD_INSTALL_DIR=/tmp/hc-cli-bin \
bash /mnt/c/projects/HOMELAB_MINI_AWS_CONSOLE/homecloud-cli/install/install.sh

kill "$PID" 2>/dev/null || true
/tmp/hc-cli-bin/homecloud version
echo "install_sh_ok"
