# Public Download Packaging

Use the tracked packaging script to reproduce the website download bundle from committed source.

## Build `latest`

```bash
bash scripts/package-public-download.sh
```

Default output:

- `dist/public-download/latest/sparkbot-latest.tar.gz`
- `dist/public-download/latest/sparkbot-latest.zip`
- `dist/public-download/latest/sparkbot-cli.py`
- `dist/public-download/latest/SHA256SUMS`
- `dist/public-download/latest/RELEASE-NOTES.txt`

## Publish to the website download directory

```bash
bash scripts/package-public-download.sh \
  --publish-dir /var/www/sparkpitlabs.com/downloads/sparkbot/latest
```

If the target directory needs elevated permissions, run the script from a shell with the necessary access.

## Build a versioned release

```bash
bash scripts/package-public-download.sh \
  --ref sparkbot-v1.2.4 \
  --artifact-prefix sparkbot-1.2.4 \
  --output-dir dist/public-download/1.2.4
```

This ties the package to a specific tag or commit instead of the current `HEAD`.

## Add release notes text

```bash
bash scripts/package-public-download.sh \
  --notes-file docs/release-notes/v1.2.4.txt
```

The script always stamps `RELEASE-NOTES.txt` with:

- version from `backend/pyproject.toml` unless overridden
- git ref used for packaging
- exact commit hash
- build timestamp

If `--notes-file` is provided, its plaintext body is appended under `Release notes:`.

## Reproducibility rules

- Packaging source is exported with `git archive`, so the bundle is built from committed source, not local junk
- Internal-only docs are removed from the staged public bundle
- Backup files, Python bytecode, cache directories, `node_modules`, and `dist` are excluded
- `SHA256SUMS` is regenerated on every run

For public download provenance, package from a tag or commit with `--ref` and keep the generated `RELEASE-NOTES.txt` and `SHA256SUMS` alongside the published artifacts.
