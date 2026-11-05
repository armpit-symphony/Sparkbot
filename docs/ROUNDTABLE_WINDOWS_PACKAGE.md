# Roundtable Windows package handoff

Signed: Atlas | 2026-11-05

## Saved baseline

Current source baseline: `3c72545`, including the Codex runner, backend job API,
and Meridian's Claude adapter fixes. Deployed server baseline remains `13e284b`.
The source snapshot branch is `roundtable/pilot-snapshot-2026-11-05` in
`sparkpit-labs/Sparkbot`. Saving source there does not merge its existing main
branch or certify an installer for release.

## First package target

Windows x64 pilot installer using the existing Tauri shell and PyInstaller
backend. Preserve hosted room support and the local SQLite backend. Ship the
connector/runner without credentials; users supply their own supported provider
installation and sign-in. Participation must be explicitly started and stoppable.

## Existing foundations and gaps

- `src-tauri/tauri.conf.json` already defines the Windows NSIS installer and a
  `sparkbot-backend` sidecar. Current branding is Sparkbot Local, version 1.6.81.
- `scripts/build-desktop.sh` supports Linux/macOS and directs Windows to CI.
- `sparkbot-backend.spec` packages the backend and dynamic dependencies; its
  listed data files do not yet explicitly include `sparkbot-roundtable.py`.
  Verify the frozen connector-download path and runner launch path before bundling.
- Rust/Cargo and Bun are available on this PC. PyInstaller was not found on PATH;
  verify the project's Python environment, Tauri CLI, MSVC and WebView2 build
  requirements before attempting the installer build.
- Foreground CLI runners currently work separately from the desktop shell.
  Packaging must supply an explicit start/stop experience and reliably stop child
  processes on exit; do not silently install an always-on service.

## Acceptance sequence

- Inspect/reuse the existing Windows CI workflow and build a reproducible unsigned
  pilot installer from a pinned commit, recording checksums and dependencies.
- Include connector assets and validate a clean-machine install with no repo,
  Python environment, saved provider session or developer credentials assumed.
- Verify local migrations, hosted-room login/invite, agent setup, presence,
  mention/reply, pause/resume, shutdown, restart and uninstall/data retention.
- Resolve RT-013 completion races and RT-012 threaded-room deletion; complete
  Claude and interrupted-job acceptance. Track RT-010 display fixes.
- Decide code signing, update delivery, commercial provider authentication and
  distribution terms before selling. A source ZIP is a developer download, not
  an installable desktop release.
