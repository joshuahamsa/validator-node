# xrpld Clean Consumer Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every maintained dashboard and MOTD consumer from rippled compatibility names to native xrpld 3.2.0 names and verify the live system end to end.

**Architecture:** Repository scripts remain configurable through `XRPLD_*` settings. The installed configuration becomes the single native xrpld binding, `install-service.sh` regenerates systemd and sudoers from it, and the standalone tmux dashboard calls xrpld directly.

**Tech Stack:** Bash, systemd, Python 3 unittest, xrpld admin RPC, jq, curl

## Global Constraints

- Do not modify or remove `/usr/local/bin/rippled` or the masked `rippled.service` compatibility artifacts.
- Do not restart `xrpld.service`.
- Back up live configuration and service files before replacing them.
- Use admin RPC endpoint `127.0.0.1:5006`.

---

### Task 1: Cut Over the Standalone Dashboard

**Files:**
- Modify: `/home/hamsa/validator-dashboard.sh`

**Interfaces:**
- Consumes: `/usr/bin/xrpld`, `xrpld.service`, admin RPC `127.0.0.1:5006`
- Produces: tmux dashboard panes backed by native xrpld commands and journal

- [ ] **Step 1: Verify the legacy-reference check fails**

Run: `rg -n 'rippled' /home/hamsa/validator-dashboard.sh`
Expected: matches for the journal, `server_info`, and `peers` commands.

- [ ] **Step 2: Replace legacy consumers**

Change `journalctl -u rippled` to `journalctl -u xrpld`. Change both `sudo rippled` commands to `sudo /usr/bin/xrpld --rpc_ip=127.0.0.1:5006`.

- [ ] **Step 3: Verify shell syntax and absence of legacy references**

Run: `bash -n /home/hamsa/validator-dashboard.sh && ! rg -n 'rippled' /home/hamsa/validator-dashboard.sh`
Expected: exit 0 with no output.

### Task 2: Deploy Native xrpld Configuration

**Files:**
- Modify: `/etc/validator-node/validator.conf`
- Regenerate: `/etc/systemd/system/metrics-server.service`
- Regenerate: `/etc/sudoers.d/metrics-server`
- Deploy: `/usr/local/bin/motd-validator-render`

**Interfaces:**
- Consumes: repository install scripts and approved native xrpld settings
- Produces: a metrics service ordered after `xrpld.service`, using `/usr/bin/xrpld` and `/etc/xrpld/xrpld.cfg`

- [ ] **Step 1: Capture timestamped backups**

Copy the current validator config, metrics unit, and sudoers file to sibling files suffixed with `.pre-xrpld-cutover-20260722T<UTC time>`.

- [ ] **Step 2: Replace the four installed bindings**

Set the installed configuration to:

```bash
XRPLD_BIN=/usr/bin/xrpld
XRPLD_UNIT=xrpld
XRPLD_CFG=/etc/xrpld/xrpld.cfg
XRPLD_ADMIN_RPC=127.0.0.1:5006
```

- [ ] **Step 3: Run repository verification before deployment**

Run: `python3 -m unittest -v test_metrics_server.py` from `motd/`, followed by `bash -n motd-validator-render install-service.sh cron-install.sh setup.sh`.
Expected: 36 tests pass and syntax checks exit 0.

- [ ] **Step 4: Regenerate live service files**

Run `sudo bash /home/hamsa/validator-node/motd/install-service.sh`, then copy the repository MOTD renderer to `/usr/local/bin/motd-validator-render` with mode 755 and execute it once.

- [ ] **Step 5: Verify installed bindings**

Confirm the installed config contains the four exact settings, the metrics unit contains `After=network.target xrpld.service`, sudoers authorizes `/usr/bin/xrpld` and `/etc/xrpld/xrpld.cfg`, and no maintained deployed file invokes legacy rippled.

### Task 3: End-to-End Live Verification

**Files:**
- Inspect: `/var/cache/motd-validator`

**Interfaces:**
- Consumes: live systemd, local RPC and metrics, public Tailscale Funnel
- Produces: evidence-backed cutover status

- [ ] **Step 1: Verify service state**

Run `systemctl is-active xrpld metrics-server` and `systemctl is-enabled xrpld metrics-server`.
Expected: both units are active and enabled.

- [ ] **Step 2: Verify native admin RPC**

Query `/usr/bin/xrpld --rpc_ip=127.0.0.1:5006 server_info` through passwordless sudo.
Expected: build version 3.2.0, a healthy server state, and a current validated ledger.

- [ ] **Step 3: Verify local and public metrics**

Query `http://127.0.0.1:8080/metrics` and `https://<your-tailnet-host>.ts.net/metrics`.
Expected: both report version 3.2.0, healthy validator data, and matching current ledger information.

- [ ] **Step 4: Verify freshly rendered MOTD**

Strip ANSI from `/var/cache/motd-validator` and inspect state, version, ledger, and alerts.
Expected: FULL, version 3.2.0, current ledger, and no cutover error.

- [ ] **Step 5: Review repository changes**

Run `git status --short` and `git diff --check`, preserving the user's pre-existing `frontend/validator.html` and `validator-tools-plugin/.orphaned_at` changes.
