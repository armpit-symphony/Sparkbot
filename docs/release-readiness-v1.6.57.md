# Sparkbot v1.6.57 Public-v1 Readiness Notes

## DNS/public wiring status

- `api.sparkpitlabs.com` did not resolve from this workstation during the May 3, 2026 check. The local resolver timed out and direct Cloudflare resolution returned no record.
- The checked-in local Compose profile binds the backend to `127.0.0.1:8000`, which keeps the API private on the host.
- The systemd example binds the backend to `127.0.0.1:8091`, which is the right shape for an nginx reverse proxy.
- The production Traefik Compose profile routes `api.${DOMAIN}` to backend port `8000`, but DNS must point at the server before that can work.

Phil must add DNS outside this repo if DNS is external:

```text
Type: A
Name: api.sparkpitlabs.com
Value: <public IPv4 address of the Sparkbot server>
TTL: 300
```

If IPv6 is enabled on the server, also add:

```text
Type: AAAA
Name: api.sparkpitlabs.com
Value: <public IPv6 address of the Sparkbot server>
TTL: 300
```

For nginx/systemd deployments, proxy the public API host to the private backend:

```nginx
server {
    server_name api.sparkpitlabs.com;

    location / {
        proxy_pass http://127.0.0.1:8091;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

TLS should be issued after DNS resolves:

```bash
sudo certbot --nginx -d api.sparkpitlabs.com
curl -f https://api.sparkpitlabs.com/api/v1/utils/health-check/
```

Keep the API private until `ENVIRONMENT=production`, real `FRONTEND_HOST`, real `BACKEND_CORS_ORIGINS`, strong auth secrets, and disabled public live terminal settings are verified.

## Production safety checklist

- `ENVIRONMENT=production`
- `FRONTEND_HOST=https://sparkpitlabs.com` or the final browser app origin
- `BACKEND_CORS_ORIGINS=https://sparkpitlabs.com` plus any other real app origins only
- No wildcard or localhost CORS origins in production
- Strong explicit `SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD`, and `SPARKBOT_PASSPHRASE`
- `WORKSTATION_LIVE_TERMINAL_ENABLED=false` for public v1
- `BACKEND_WORKERS=2`

## Provider keys and secrets

Provider keys in the live container environment are normal operationally, but old testing/debugging keys should be rotated before public release. Rotate in each provider console, update the server `.env` or Guardian Vault entry, restart only the affected service, then verify chat/provider health. Do not commit real `.env` files or provider keys.

Sparkbot already has Guardian Vault for connector/provider secrets. The migration path is to store long-lived provider and connector secrets as `use_only` Vault entries, keep only non-secret toggles and IDs in env files, and reserve `privileged_reveal`/break-glass for operator recovery.

## Worker and background-job safety

Web/API workers are for HTTP and WebSocket responsiveness. Long-running work should move to separate task workers or a queue. Any recurring background job must be leader-locked or run in a dedicated singleton worker. Do not increase API workers above 2 until Guardian jobs, bridge polling, reminders, live terminal, browser control, shell/code execution, multi-agent rooms, and push channels are audited and load-tested.

## Polish notes

- Frontend build currently warns about a large main chunk. Code-splitting chat, workstation, and terminal surfaces is recommended polish, not a public-v1 blocker.
- Pydantic and FastAPI lifecycle deprecation warnings should be cleaned up before future dependency upgrades. Treat this as polish unless a dependency upgrade makes it blocking.
