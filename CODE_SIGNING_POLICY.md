# Code Signing Policy — Sparkbot

## Overview

Sparkbot is an open-source AI assistant platform licensed under the MIT License.
Desktop builds (Windows, macOS, Linux) are distributed via GitHub Releases.

## Windows Authenticode Signing

Sparkbot is set up to sign Windows desktop releases through the
[SignPath Foundation](https://signpath.org) Open Source program when the
required GitHub Actions secrets are configured.

### What is signed

- The Windows NSIS installer published on GitHub Releases (`*-setup.exe`)

### How signing works

On tag builds matching `desktop-v*`, the desktop release workflow:

1. Builds the unsigned Windows installer on a GitHub-hosted runner
2. Uploads the unsigned installer as a GitHub Actions artifact
3. Submits a signing request to SignPath via the official GitHub Action when the SignPath secrets are present
4. Waits for SignPath approval and completion
5. Publishes the signed installer to GitHub Releases
6. Falls back to the unsigned installer only when signing is not configured for that build

The SignPath connector cryptographically verifies that artifacts were produced
by this repository's CI workflow and were not tampered with.

### Required secrets

- `SIGNPATH_API_TOKEN`
- `SIGNPATH_ORG_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_SIGNING_POLICY_SLUG`
- `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` (optional)

### Who can approve signing requests

Signing requests may require approval from a designated approver before
SignPath will sign. The intended approver is the repository maintainer
(`armpit-symphony`).

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
