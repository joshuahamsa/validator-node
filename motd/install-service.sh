#!/usr/bin/env bash
# Deploy metrics-server systemd service + sudoers.
# Run as: sudo bash install-service.sh
# Requires /etc/validator-node/validator.conf — run motd/setup.sh first.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run with sudo: sudo bash $0"
    exit 1
fi

SYSTEM_CONFIG="/etc/validator-node/validator.conf"
if [[ ! -f "$SYSTEM_CONFIG" ]]; then
    echo "ERROR: $SYSTEM_CONFIG not found. Run motd/setup.sh first."
    exit 1
fi
source "$SYSTEM_CONFIG"

echo "=== Writing /etc/systemd/system/metrics-server.service ==="
cat > /etc/systemd/system/metrics-server.service <<EOF
[Unit]
Description=XRPL Validator Metrics HTTP Server
After=network.target ${XRPLD_UNIT:-xrpld}.service

[Service]
Type=simple
User=${VALIDATOR_USERNAME}
EnvironmentFile=${SYSTEM_CONFIG}
ExecStart=/usr/bin/python3 ${REPO_PATH}/motd/metrics_server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
echo "  done."

echo "=== Writing /etc/sudoers.d/metrics-server ==="
cat > /etc/sudoers.d/metrics-server <<EOF
${VALIDATOR_USERNAME} ALL=(ALL) NOPASSWD: ${XRPLD_BIN:-/usr/bin/xrpld}
${VALIDATOR_USERNAME} ALL=(ALL) NOPASSWD: /usr/local/bin/rapl-energy-uj
${VALIDATOR_USERNAME} ALL=(ALL) NOPASSWD: /usr/bin/cat ${XRPLD_CFG:-/etc/xrpld/xrpld.cfg}
EOF
chmod 0440 /etc/sudoers.d/metrics-server
visudo -c
echo "  done."

echo "=== Enabling and starting metrics-server ==="
systemctl daemon-reload
systemctl enable metrics-server
systemctl restart metrics-server
sleep 2
systemctl status metrics-server

echo ""
echo "=== Verifying endpoint ==="
curl -s http://127.0.0.1:8080/metrics | python3 -m json.tool | grep -E '"state"|"ledger_seq"'
echo ""
echo "=== Done. metrics-server live at http://127.0.0.1:8080/metrics ==="
