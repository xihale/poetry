# gx deploy — shared webhook receiver

This site deploys on push via the shared receiver on gx: GitHub webhook →
adnanh/webhook (/etc/webhook/hooks.json whitelist, HMAC + pinned branch) →
sudo → /usr/local/lib/webhook-deploy → deploy.sh in this directory.
The per-site webhook.mjs was removed on 2026-10-11 when all five sites
moved onto the shared receiver.

Ops notes (whitelist, sudoers, adding a site): scripts/server/README.md in
xihale/zig-playground.
