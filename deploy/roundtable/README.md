# RT-005 isolated hosting

Owner: Atlas. Signed: Atlas | 2026-10-25.

## Current deployment: runner pilot, 2026-11-04

- Deployed source `13e284b`, image pair `13e284b-pilot`, server `.env` image pin
  updated. Prestart successfully applied additive migration `5e7a1c3d9b20`
  (three new runner tables). Signed: Atlas | 2026-11-04
- Backup `/home/sparky/rtpilot-backup-13e284b`: private environment snapshot,
  PostgreSQL dump restored successfully into a temporary database, and validated
  data/uploads archive. Scratch database removed after verification. Prior image
  pair retained as `prepilot-13e284b`. Signed: Atlas | 2026-11-04
- Validation: 34 backend job/connector/seat tests passed in a disposable
  network-isolated container; frontend build and HTTPS smoke passed. Live
  PostgreSQL job checks passed sequential idempotency, pause/resume, stale claims
  and retry. Browser verified Atlas online, Pause/Resume and guest messaging.
  Original Sparkbot/TNT stayed healthy; homepage hash unchanged.
  Signed: Atlas | 2026-11-04
- Atlas's PC foreground runner is active at this snapshot; Phil's 9:42 PM ET
  mention received an automatic reply in the same minute. It is not a server
  service and will not automatically restart with the PC. See
  `../../docs/roundtable-codex-pilot.md`. Signed: Atlas | 2026-11-04
- Open defects: RT-012 PostgreSQL deletion of rooms with threaded replies;
  RT-013 completion is two persistence steps, so concurrent completion/pause
  races remain unverified. The synthetic deletion failure was cleaned up only
  after checking its exact room ID/name and clearing that room's reply links.
  No real team-room data was changed. Signed: Atlas | 2026-11-04

Code rollback, from `/home/sparky/sparkbot-roundtable-atlas`:

```sh
RT_IMAGE_TAG=prepilot-13e284b docker compose --env-file deploy/roundtable/.env -f deploy/roundtable/compose.yml up -d --no-deps backend frontend
```

Stop the PC runner before rolling back the backend. If retaining rollback, pin
the server `.env` to `prepilot-13e284b`. This command preserves the additive tables
and messages and skips prestart; it is not a database downgrade. Do not restore
the backup or drop new tables without reviewing writes since deployment.
Signed: Atlas | 2026-11-04

## Earlier deployment history

RT-008 source baseline: `f3f1edf`, plus the committed hosted-path/deployment files. Server checkout:
`/home/sparky/sparkbot-roundtable-atlas`. Compose project: `sparkbot-roundtable`.
This is a test deployment, not a public-release certification.

Default image tag is `f3f1edf-rt008`; `RT_IMAGE_TAG` can select a pinned pair
of backend/frontend images for a later release or rollback. Preserve previous
images and a private PostgreSQL/data backup before updating an existing stack.

Current URL: `https://sparkpitlabs.com/roundtable/`. Phil selected the existing
site on 2026-10-25. Frontend builds with `VITE_APP_BASE_PATH=/roundtable/`;
the API stays at `/api/v1/` on that origin. The homepage stays unchanged.
`existing-site.locations.conf` is installed at
`/etc/nginx/snippets/roundtable-atlas.conf`, included by the existing HTTPS site.
The pre-change site backup is outside nginx's include directories at
`/etc/nginx/rt005-backups/sparkpitlabs.com.before-roundtable.conf`.
Browser acceptance passed on 2026-11-04: owner login, existing Atlas message,
People & agents panel, Person invite, guest posting, live refresh, model-free
owner reply, and guest revocation. `browser-smoke.cjs` repeats this with the
host's installed Playwright and an in-memory `RT_OWNER_PASSPHRASE`; it creates
and removes a disposable room and never saves keys, cookies, or traces.

RT-008 rollback evidence: `/home/sparky/rt008-backup-20261104` holds a private
database dump (restored successfully into a scratch database), app data/uploads,
and original deployment configuration. Prior backend/frontend images are tagged
`pre-rt008-20261104`. To roll back code without touching volumes, use:

```sh
RT_IMAGE_TAG=pre-rt008-20261104 docker compose --env-file deploy/roundtable/.env -f deploy/roundtable/compose.yml up -d --no-deps backend frontend
```

The RT-008 upgrade adds no schema migration. Restore data only after separately
reviewing any writes made since backup; code rollback alone preserves messages.

## Configuration

The server-only `deploy/roundtable/.env` is mode 0600 and is not committed.
Use independently generated database, owner, and signing secrets. Never print
the environment or run `docker compose config` without `--quiet` in shared logs.
No provider credentials or existing deployment credentials are copied.

Use production mode, `V1_LOCAL_MODE=false`, live terminal disabled, and one
backend worker (seat rate limits are in-process). Configure the final HTTPS
origin in `FRONTEND_HOST` and `BACKEND_CORS_ORIGINS` before publishing access.
Core reminder/Guardian maintenance loops are part of app startup; this fresh
database has no scheduled customer tasks or configured outbound connectors.

Database, uploads, and app data have separate named volumes. No existing
Sparkbot/TNT volume, host cron/proc/log folder, or provider-auth file is mounted.
Backend and frontend bind only to 127.0.0.1 ports 8002 and 3002.

## Build, start, check

Run from the server checkout:

```sh
docker compose --env-file deploy/roundtable/.env -f deploy/roundtable/compose.yml config --quiet
docker compose --env-file deploy/roundtable/.env -f deploy/roundtable/compose.yml build
docker compose --env-file deploy/roundtable/.env -f deploy/roundtable/compose.yml up -d
docker compose --env-file deploy/roundtable/.env -f deploy/roundtable/compose.yml ps
python3 deploy/roundtable/smoke.py
python3 deploy/roundtable/smoke.py --https
```

The smoke script reads only this deployment's secret file, creates disposable
rooms/participants, verifies seat authorization/revocation, then deletes its
rooms. It prints no keys or tokens. It does not invoke models or post to real
team rooms. It does not prove a working multi-human browser experience.

## Publish after preflight

Confirm the hostname resolves to this droplet and obtain a matching TLS
certificate. Adapt `nginx.conf.template` into its own site, check `nginx -t`,
then reload nginx. Keep existing site files intact. Check HTTPS login, websocket
upgrades, cross-room denial and revocation, then existing Sparkbot/TNT health.
Guest browser participation still depends on RT-007; agent setup on RT-004.
Owner passphrase belongs only to Phil; guests get room-scoped seat keys.

## Rollback

Remove only the `roundtable-atlas.conf` include from the existing HTTPS site,
run `nginx -t`, and reload nginx. The backup can be used only after verifying
that it will not overwrite subsequent unrelated site changes.
Stop only this project; do not add `-v`, prune images/volumes, or stop other stacks:

```sh
docker compose --env-file deploy/roundtable/.env -f deploy/roundtable/compose.yml stop
```

Fresh deployment volumes remain available for inspection/restart. No rollback
of the original Sparkbot database is needed because it is not reused. Before
any future replacement or upgrade containing real meeting data, capture a
database dump plus data/uploads and prove restoration in a separate project.
