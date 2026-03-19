# Code Signing Policy — Sparkbot

## Overview

Sparkbot is an open-source AI assistant platform licensed under the MIT License.
Desktop builds (Windows, macOS, Linux) are distributed via GitHub Releases.

## Windows Authenticode Signing

Windows desktop builds are signed using a certificate issued by the
[SignPath Foundation](https://signpath.org) under their free Open Source program.

### What is signed

- `sparkbot-backend.exe` — the PyInstaller-packaged FastAPI backend sidecar
- `sparkbot-local-shell.exe` — the Tauri desktop shell
- The NSIS installer (`*-setup.exe`)

### How signing works

Signing is performed automatically by GitHub Actions on every tag matching
`desktop-v*`. The build workflow:

1. Builds all binaries on GitHub-hosted runners (no self-hosted runners)
2. Uploads artifacts to GitHub
3. Submits a signing request to SignPath via the official GitHub Action
4. SignPath verifies the artifact was produced by this repository's workflow
5. Signs and returns the artifacts
6. The signed installer is published to GitHub Releases

The SignPath connector cryptographically verifies that artifacts were produced
by this repository's CI workflow and were not tampered with.

### Who can approve signing requests

Signing requests require approval from a designated Approver before SignPath
will sign. The Approver is the repository maintainer (`armpit-symphony`).

## Verification

Every release includes a `SHA256SUMS` file. Verify your download:

```sh
# Windows (PowerShell)
Get-FileHash Sparkbot.Local_*_x64-setup.exe -Algorithm SHA256

# macOS / Linux
sha256sum --check SHA256SUMS
```

## Reporting Issues

If you believe a signed release has been tampered with or contains malware,
open an issue at https://github.com/armpit-symphony/Sparkbot/issues
