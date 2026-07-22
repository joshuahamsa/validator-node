# xrpld Clean Consumer Cutover Design

## Goal

Complete the validator dashboard and MOTD migration to xrpld 3.2.0 by making every maintained consumer use the native xrpld binary, systemd unit, configuration file, and admin RPC endpoint.

## Scope

The cutover updates the installed validator configuration, the generated metrics-server unit, and the standalone tmux dashboard. It then redeploys the affected service and MOTD renderer. Package-managed compatibility artifacts such as `/usr/local/bin/rippled` and the masked `rippled.service` remain untouched because maintained tooling will no longer depend on them.

## Configuration and Service Behavior

`/etc/validator-node/validator.conf` will select:

- `XRPLD_BIN=/usr/bin/xrpld`
- `XRPLD_UNIT=xrpld`
- `XRPLD_CFG=/etc/xrpld/xrpld.cfg`
- `XRPLD_ADMIN_RPC=127.0.0.1:5006`

Re-running `motd/install-service.sh` will regenerate `metrics-server.service` with `After=network.target xrpld.service`, refresh sudoers with the xrpld binary and configuration paths, reload systemd, and restart metrics-server. The xrpld daemon itself does not need a restart.

## Dashboard and MOTD

`validator-dashboard.sh` will replace direct `rippled` commands and the `rippled` journal with `/usr/bin/xrpld`, the xrpld journal, and explicit `--rpc_ip=127.0.0.1:5006` for RPC calls. The deployed MOTD renderer will be refreshed from the repository and run once to regenerate `/var/cache/motd-validator`.

## Safety and Error Handling

Before deployment, the current system configuration and unit files will be copied to timestamped backup files. Deployment stops on command failure. Existing `rippled` compatibility artifacts will not be deleted or modified. Only metrics-server will be restarted as part of the cutover.

## Verification

Verification requires all of the following:

- Repository tests and shell syntax checks pass.
- `xrpld.service` and `metrics-server.service` are active and enabled.
- The installed metrics unit orders after `xrpld.service` and contains no `rippled.service` reference.
- Installed validator configuration contains only the native xrpld paths for the four `XRPLD_*` settings.
- Local admin RPC reports version 3.2.0 and a live validated ledger.
- Local and public metrics endpoints report version 3.2.0, a healthy validator state, amendments, and current ledger data.
- A freshly rendered MOTD reports version 3.2.0 and a healthy validator state.
- Maintained runtime files contain no executable or service references to legacy rippled; historical comments, compatibility fallbacks, test fixtures, and JSON field names remain permitted.
