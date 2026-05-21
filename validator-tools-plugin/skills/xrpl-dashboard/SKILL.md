---
name: xrpl-dashboard
description: Use this skill when working on the XRPL validator node dashboard, metrics server, amendment voting, or any rippled interaction on letseffinggo. Covers debugging the /metrics endpoint, amendment vote display, the amend CLI, service management, sudoers, and the admin RPC. Trigger on any mention of: dashboard, amendments, metrics-server, amend CLI, rippled feature, validator, wallet.db, vetoed, motd, metrics endpoint.
---

# XRPL Validator Dashboard — Working Knowledge

## Architecture

```
rippled (port 5006 admin RPC)
    ↓ sudo rippled --rpc_ip=127.0.0.1:5006 feature/server_info
metrics_server.py  →  GET /metrics  →  http://127.0.0.1:8080/metrics
    ↓
motd-validator-render (bash, called on SSH login)
```

All files live at `/home/hamsa/validator-node/motd/`.

## Key Commands

### Check metrics endpoint
```bash
curl -s http://127.0.0.1:8080/metrics | python3 -m json.tool | grep -A3 '"amendments"'
```

### Check amendment vote state (ground truth)
```bash
sudo rippled --rpc_ip=127.0.0.1:5006 feature \
  | jq '.result.features | to_entries
        | map(select(.value.enabled == false and .value.vetoed != "Obsolete"))
        | from_entries'
```

### Service management
```bash
sudo systemctl status metrics-server
sudo systemctl restart metrics-server
sudo journalctl -u metrics-server -n 50 --no-pager
```

### Run tests
```bash
cd /home/hamsa/validator-node/motd && python3 -m pytest test_amend_lib.py -v
```

### Deploy / reinstall
```bash
sudo bash /home/hamsa/validator-node/motd/install-service.sh  # metrics-server service + sudoers
sudo bash /home/hamsa/validator-node/motd/install-amend.sh    # amend CLI + sudoers
```

### Interactive amendment voting CLI
```bash
amend
```

## Amendment Vote Logic

The admin RPC returns a `vetoed` field per pending amendment:
- `vetoed: false`  → node votes **YES**
- `vetoed: true`   → node votes **NO**  
- `vetoed: "Obsolete"` → **skip** (filtered out of display)
- `enabled: true`  → **skip** (already active)

**Do not** read wallet.db or rippled.cfg to determine vote state — the admin RPC already synthesizes both.

## Critical Lessons

### `--rpc_ip=127.0.0.1:5006` is required for complete data
Without this flag, `rippled feature` omits the `vetoed` field entirely for non-vetoed amendments. With it, every amendment gets `vetoed: true/false/"Obsolete"`. Always use the flag.

### sudoers: no `=` signs in argument specs
`hamsa ALL=(ALL) NOPASSWD: /usr/local/bin/rippled --rpc_ip=127.0.0.1:5006 feature` → **syntax error**.  
Use bare path: `hamsa ALL=(ALL) NOPASSWD: /usr/local/bin/rippled` (no args = any args allowed).

### Service changes need a restart
`systemctl start` is a no-op if service is running. Always use `systemctl restart` after code or config changes.

### amend CLI writes to rippled.cfg; rippled picks it up on restart
The `amend` CLI writes amendment votes to `/etc/opt/ripple/rippled.cfg`. rippled synthesizes those into the `vetoed` field on its next restart. Until restart, the RPC still reflects the pre-vote state.

## Sudoers Setup

**metrics-server** (`/etc/sudoers.d/metrics-server`):
```
hamsa ALL=(ALL) NOPASSWD: /usr/local/bin/rippled
hamsa ALL=(ALL) NOPASSWD: /usr/local/bin/rapl-energy-uj
```

**amend CLI** (`/etc/sudoers.d/amend`):
```
hamsa ALL=(ALL) NOPASSWD: /usr/local/bin/rippled
hamsa ALL=(ALL) NOPASSWD: /usr/bin/cat /etc/opt/ripple/rippled.cfg
hamsa ALL=(ALL) NOPASSWD: /usr/bin/cp /etc/opt/ripple/rippled.cfg /etc/opt/ripple/rippled.cfg.bak
hamsa ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/opt/ripple/rippled.cfg
hamsa ALL=(ALL) NOPASSWD: /bin/systemctl restart rippled
hamsa ALL=(ALL) NOPASSWD: /bin/journalctl -u rippled -n 20 --no-pager
```

## File Map

| File | Purpose |
|------|---------|
| `metrics_server.py` | HTTP server, `GET /metrics` → JSON |
| `amend_lib.py` | Shared: `get_live_features()`, `compute_working_set()`, `write_cfg_vote()` |
| `amend` | Interactive TUI (rich + prompt_toolkit), Python venv at `~/.venv` |
| `test_amend_lib.py` | Unit tests for amend_lib |
| `install-service.sh` | systemd unit + sudoers for metrics-server |
| `install-amend.sh` | amend CLI install + sudoers |
