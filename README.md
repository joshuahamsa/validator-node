# XRPL Validator Node Tooling

Terminal dashboard, JSON metrics endpoint, and amendment voting CLI for an XRPL validator node running on Ubuntu with rippled.

On every SSH login you get a live dashboard showing validator state, system resources, amendment votes, and network info. The same data is served as JSON at `http://127.0.0.1:8080/metrics` for use by external dashboards or monitoring tools.

---

## What You Get

**SSH login dashboard** (rendered to MOTD every 30s via cron):
- Validator state, ledger seq, peer count, uptime
- CPU / RAM / disk usage with progress bars, CPU temperature, CPU power draw (Intel RAPL)
- LAN + Tailscale IP, SSH session count, P2P port status
- Pending amendment list with your current vote (YES/NO) and network majority status
- Recent rippled warnings/errors

**`GET /metrics` JSON endpoint** (port 8080, localhost):
- Same data as above in machine-readable JSON, with CORS enabled

**`amend` CLI**:
- Interactive TUI for reviewing pending XRPL amendments and writing votes to `rippled.cfg`

---

## Prerequisites

- Ubuntu 22.04+ (or similar Debian-based distro)
- [`rippled`](https://xrpl.org/install-rippled-on-ubuntu.html) installed and synced, admin RPC on `127.0.0.1:5006`
- Python 3.10+
- `sensors` (lm-sensors) for CPU temperature: `sudo apt install lm-sensors`
- Intel CPU with RAPL support for power metrics (optional — skipped gracefully if absent)
- [Tailscale](https://tailscale.com/download/linux) installed if you want the metrics endpoint accessible over the internet via Funnel

---

## Installation

Clone the repo and run the install scripts in order. All scripts require `sudo`.

```bash
git clone https://github.com/joshuahamsa/validator-node.git
cd validator-node/motd
```

### 1. Metrics server (core)

Installs the systemd service that serves `/metrics` on port 8080, and writes sudoers entries so it can call `rippled` without a password.

```bash
sudo bash install-service.sh
```

**Adapt for your username:** The service runs as `hamsa` and references `/home/hamsa/validator-node/motd/metrics_server.py`. Edit `install-service.sh` before running — replace `hamsa` with your username in the `User=` line, the `ExecStart=` path, and all sudoers entries.

Also set your validator JSON path in `metrics_server.py`:
```python
_json_files = list(Path("/home/hamsa/.ripple").glob("*.json"))
```
Change `/home/hamsa/.ripple` to wherever your validator key JSON is stored.

### 2. RAPL CPU power metrics (optional)

Installs a tiny wrapper script that reads Intel RAPL energy counters. Skip this if you don't have an Intel CPU or don't want power draw metrics.

```bash
sudo bash install-rapl.sh
```

### 3. MOTD dashboard

Installs the cron job (runs every 30s as root) and hooks it into `/etc/update-motd.d/` so the dashboard renders on SSH login.

```bash
sudo cp motd-validator-render /usr/local/bin/motd-validator-render
sudo chmod 755 /usr/local/bin/motd-validator-render
sudo bash cron-install.sh
```

**Adapt for your username:** `motd-validator-render` calls `curl http://127.0.0.1:8080/metrics` — no username dependency there. But it does read a `VALIDATOR_JSON` path at the top of the file if you have one hardcoded. Review the top of the script before copying.

### 4. Amendment voting CLI (optional)

Installs the `amend` interactive TUI and its sudoers entries (needed to read/write `rippled.cfg`).

```bash
# Install Python dependencies into a venv first
python3 -m venv ~/.venv
~/.venv/bin/pip install rich prompt_toolkit

sudo bash install-amend.sh
```

**Adapt for your username:** Edit `install-amend.sh` — replace `hamsa` in sudoers entries and in the `cp` destination paths. Also update the shebang in `amend`:
```
#!/home/hamsa/.venv/bin/python3  →  #!/home/YOUR_USER/.venv/bin/python3
```

---

## Tailscale Funnel (required for remote access)

The metrics server binds to `127.0.0.1:8080` — localhost only. To access the JSON endpoint from outside the machine (e.g. from a browser-based dashboard or another device on your tailnet), use **Tailscale Funnel**:

```bash
tailscale funnel 8080
```

This exposes `https://<your-hostname>.ts.net/metrics` publicly over HTTPS. The endpoint has CORS enabled so it can be consumed directly from a browser.

To make Funnel persistent across reboots:

```bash
tailscale funnel --bg 8080
```

To check or remove it:

```bash
tailscale funnel status
tailscale funnel reset
```

> **Note:** Tailscale Funnel requires a Tailscale account with Funnel enabled. See [Tailscale Funnel docs](https://tailscale.com/kb/1223/funnel).

---

## Using the `amend` CLI

Run `amend` to review pending amendments and record your votes:

```bash
amend
```

Navigate with `↑`/`↓` or `j`/`k`. Vote with `y` (YES) or `n` (NO). Write a vote to `rippled.cfg` with `w`. Restart rippled with `R` to apply. Quit with `q`.

Votes are written to the `[amendments]` or `[veto_amendments]` sections of `/etc/opt/ripple/rippled.cfg`. rippled applies them on restart. The dashboard reflects the new vote state after rippled restarts (it reads the synthesized `vetoed` field from `rippled --rpc_ip=127.0.0.1:5006 feature`).

---

## Verifying the Endpoint

```bash
curl -s http://127.0.0.1:8080/metrics | python3 -m json.tool | grep -E '"state"|"ledger_seq"|"amendments"' 
```

Check amendment votes specifically:

```bash
sudo rippled --rpc_ip=127.0.0.1:5006 feature \
  | jq '.result.features
    | to_entries
    | map(select(.value.enabled == false and .value.vetoed != "Obsolete"))
    | from_entries'
```

---

## Service Management

```bash
sudo systemctl status metrics-server
sudo systemctl restart metrics-server
sudo journalctl -u metrics-server -n 50 --no-pager
```

---

## Running Tests

```bash
cd motd
python3 -m pytest test_amend_lib.py -v
```

---

## File Overview

```
motd/
├── metrics_server.py       # HTTP server → GET /metrics (JSON)
├── amend_lib.py            # Shared: rippled RPC, vote logic, cfg writes
├── amend                   # Interactive amendment voting CLI
├── motd-validator-render   # Bash script → renders ANSI dashboard to /var/cache/motd-validator
├── install-service.sh      # Deploy metrics-server systemd unit + sudoers
├── install-amend.sh        # Deploy amend CLI + sudoers
├── install-rapl.sh         # Deploy RAPL CPU power reader
├── cron-install.sh         # Deploy cron job + MOTD hook
└── test_amend_lib.py       # Unit tests for amend_lib
```
