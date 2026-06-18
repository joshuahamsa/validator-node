#!/usr/bin/env bash
# Install RAPL reader wrapper + update sudoers for CPU power metrics.
# Run as: sudo bash install-rapl.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run this script with sudo: sudo bash $0"
  exit 1
fi

# Load config so the sudoers rules match the node binary/cfg this host uses.
SYSTEM_CONFIG="/etc/validator-node/validator.conf"
[[ -f "$SYSTEM_CONFIG" ]] && source "$SYSTEM_CONFIG" || true
VALIDATOR_USERNAME="${VALIDATOR_USERNAME:-hamsa}"
XRPLD_BIN="${XRPLD_BIN:-${RIPPLED_BIN:-/usr/bin/xrpld}}"
XRPLD_CFG="${XRPLD_CFG:-${RIPPLED_CFG:-/etc/xrpld/xrpld.cfg}}"

echo "=== Writing /usr/local/bin/rapl-energy-uj ==="
tee /usr/local/bin/rapl-energy-uj > /dev/null << 'EOF'
#!/bin/sh
cat /sys/class/powercap/intel-rapl:0/energy_uj
EOF
chmod 0755 /usr/local/bin/rapl-energy-uj
echo "  done."

# Rewrite the full metrics-server sudoers (keep it in sync with install-service.sh
# so this never drops the binary or cfg-read grants the dashboard depends on).
echo "=== Updating /etc/sudoers.d/metrics-server ==="
tee /etc/sudoers.d/metrics-server > /dev/null <<EOF
${VALIDATOR_USERNAME} ALL=(ALL) NOPASSWD: ${XRPLD_BIN}
${VALIDATOR_USERNAME} ALL=(ALL) NOPASSWD: /usr/local/bin/rapl-energy-uj
${VALIDATOR_USERNAME} ALL=(ALL) NOPASSWD: /usr/bin/cat ${XRPLD_CFG}
EOF
chmod 0440 /etc/sudoers.d/metrics-server
visudo -c
echo "  done."

echo "=== Restarting metrics-server ==="
systemctl restart metrics-server
sleep 2
systemctl status metrics-server --no-pager

echo ""
echo "=== Verifying cpu_w in endpoint ==="
echo "(first request sets baseline — cpu_w will be null; wait 5s and try again)"
curl -s http://127.0.0.1:8080/metrics | python3 -m json.tool | grep '"cpu_w"'
sleep 6
curl -s http://127.0.0.1:8080/metrics | python3 -m json.tool | grep '"cpu_w"'
echo ""
echo "=== Done ==="
