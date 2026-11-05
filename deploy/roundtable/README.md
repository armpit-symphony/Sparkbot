# RT-005 isolated hosting

Owner: Atlas. Signed: Atlas | 2026-10-25.

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
