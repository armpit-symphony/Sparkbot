"""Operator security posture and guarded local hardening actions."""
from __future__ import annotations

import json
import os
import re
import stat
import time
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.core.config import settings
from app.crud import create_audit_log
from app.services.guardian import get_guardian_suite

router = APIRouter(tags=["chat-security"])

_ENV_UPDATE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
_PUBLIC_FRONTEND_HEADERS = {
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
}
_RISKY_FEATURE_ENV = {
    "live_terminal": "WORKSTATION_LIVE_TERMINAL_ENABLED",
    "robotics_bridge": "LIMA_ROBOTICS_ENABLED",
    "global_computer_control": "SPARKBOT_GLOBAL_COMPUTER_CONTROL",
    "telegram_bridge": "TELEGRAM_ENABLED",
    "discord_bridge": "DISCORD_ENABLED",
    "whatsapp_bridge": "WHATSAPP_ENABLED",
    "github_bridge": "GITHUB_ENABLED",
}
_WEAK_PASSPHRASES = {
    "",
    "admin",
    "admin123",
    "changethis",
    "changeme",
    "changeme-in-production",
    "letmein",
    "letmein12345",
    "password",
    "replace_with_admin_password",
    "replace_with_strong_passphrase",
    "sparkbot-local",
    "sparkbot",
    "weak",
}


class PassphraseUpdate(BaseModel):
    passphrase: str = Field(..., min_length=16, max_length=256)


class OperatorUsersUpdate(BaseModel):
    usernames: list[str] = Field(default_factory=list, max_length=50)


class OperatorPinUpdate(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6)
    pin_confirm: str = Field(..., min_length=6, max_length=6)
    current_pin: str | None = Field(default=None, max_length=128)


class FeatureTogglesUpdate(BaseModel):
    features: dict[str, bool] = Field(default_factory=dict)


def _require_operator(current_user: CurrentChatUser) -> None:
    if not get_guardian_suite().auth.is_operator_identity(
        username=current_user.username,
        user_type=current_user.type,
    ):
        raise HTTPException(status_code=403, detail="Operator access required.")


def _require_privileged(current_user: CurrentChatUser) -> None:
    _require_operator(current_user)
    if not get_guardian_suite().auth.get_active_session(str(current_user.id)):
        raise HTTPException(
            status_code=403,
            detail="Active operator break-glass session required for this security change.",
        )


def _data_env_path() -> Path:
    data_dir = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir).expanduser() / ".env"
    return Path(__file__).resolve().parents[5] / ".env"


def _managed_env_paths() -> list[Path]:
    raw = os.getenv("SPARKBOT_SECURITY_ENV_FILES", "").strip()
    paths = [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]
    defaults = [
        _data_env_path(),
        Path(__file__).resolve().parents[5] / ".env",
        Path(__file__).resolve().parents[5] / ".env.local",
    ]
    out: list[Path] = []
    for path in [*paths, *defaults]:
        if path not in out:
            out.append(path)
    return out


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _ENV_UPDATE_RE.match(line.strip())
            if match:
                values[match.group(1)] = line.strip()[match.end() :]
    except Exception:
        return {}
    return values


def _write_env_updates(updates: dict[str, str]) -> Path:
    env_path = _data_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    pending = {key: str(value).replace("\r", "").replace("\n", "").strip() for key, value in updates.items()}
    rendered: list[str] = []

    for line in existing_lines:
        match = _ENV_UPDATE_RE.match(line.strip())
        if not match:
            rendered.append(line)
            continue
        key = match.group(1)
        if key not in pending:
            rendered.append(line)
            continue
        rendered.append(f"{key}={pending.pop(key)}")

    for key, value in pending.items():
        rendered.append(f"{key}={value}")

    env_path.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    for key, value in updates.items():
        os.environ[key] = str(value)
    return env_path


def _audit(session: SessionDep, current_user: CurrentChatUser, action: str, payload: dict[str, Any]) -> None:
    try:
        create_audit_log(
            session=session,
            tool_name=f"security_{action}",
            tool_input=json.dumps(payload, sort_keys=True),
            tool_result="ok",
            user_id=current_user.id,
        )
    except Exception:
        pass


def _passphrase_score(value: str) -> dict[str, Any]:
    normalized = (value or "").strip()
    classes = sum(
        bool(re.search(pattern, normalized))
        for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]")
    )
    weak = normalized.lower() in _WEAK_PASSPHRASES
    length = len(normalized)
    score = 0
    if length >= 16:
        score += 1
    if length >= 24:
        score += 1
    if classes >= 3:
        score += 1
    if not weak:
        score += 1
    if length >= 32:
        score += 1
    label = "strong" if score >= 4 else "fair" if score >= 3 else "weak"
    return {
        "configured": bool(normalized),
        "length": length,
        "classes": classes,
        "weak_default": weak,
        "score": score,
        "label": label,
    }


def _file_status(path: Path) -> dict[str, Any]:
    try:
        st = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False, "manageable": False}
    except PermissionError:
        return {"path": str(path), "exists": True, "manageable": False, "error": "permission denied"}
    mode = stat.S_IMODE(st.st_mode)
    return {
        "path": str(path),
        "exists": True,
        "manageable": os.access(path, os.R_OK | os.W_OK),
        "mode": f"{mode:03o}",
        "secure": mode & 0o077 == 0,
    }


def _frontend_header_status() -> dict[str, Any]:
    candidates = ["http://frontend/"]
    port = os.getenv("SPARKBOT_FRONTEND_PORT", "").strip()
    if port:
        candidates.append(f"http://host.docker.internal:{port}/")
    frontend_host = (settings.FRONTEND_HOST or "").strip()
    if frontend_host:
        candidates.append(frontend_host.rstrip("/") + "/")

    for url in candidates:
        try:
            request = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(request, timeout=2.0) as response:
                headers = {k.lower(): v for k, v in response.headers.items()}
            present = sorted(h for h in _PUBLIC_FRONTEND_HEADERS if h in headers)
            return {
                "checked": True,
                "url": url,
                "present": present,
                "missing": sorted(_PUBLIC_FRONTEND_HEADERS - set(present)),
                "ok": len(present) == len(_PUBLIC_FRONTEND_HEADERS),
            }
        except Exception:
            continue
    return {
        "checked": False,
        "present": [],
        "missing": sorted(_PUBLIC_FRONTEND_HEADERS),
        "ok": False,
        "note": "Frontend headers could not be checked from this backend runtime.",
    }


def _provider_secret_status() -> list[dict[str, Any]]:
    env_map = {
        "OpenRouter": "OPENROUTER_API_KEY",
        "OpenAI": "OPENAI_API_KEY",
        "Anthropic": "ANTHROPIC_API_KEY",
        "Google": "GOOGLE_API_KEY",
        "Groq": "GROQ_API_KEY",
        "MiniMax": "MINIMAX_API_KEY",
        "xAI": "XAI_API_KEY",
    }
    try:
        from app.services.guardian.vault import vault_get_metadata
    except Exception:
        vault_get_metadata = None  # type: ignore[assignment]

    items: list[dict[str, Any]] = []
    for label, env_key in env_map.items():
        value = os.getenv(env_key, "").strip()
        vault_alias = env_key.lower()
        vault_configured = False
        if vault_get_metadata:
            try:
                vault_configured = bool(vault_get_metadata(vault_alias))
            except Exception:
                vault_configured = False
        items.append(
            {
                "provider": label,
                "env_key": env_key,
                "configured_in_env": bool(value),
                "masked": f"{value[:4]}...{value[-4:]}" if len(value) >= 12 else "",
                "vault_alias": vault_alias,
                "configured_in_vault": vault_configured,
            }
        )
    return items


def _deployment_guidance() -> list[dict[str, str]]:
    return [
        {"area": "DNS and TLS", "operator_action": "Terminate HTTPS at your reverse proxy or edge provider."},
        {"area": "Cloudflare / Nginx access", "operator_action": "Protect public prototypes with Access or Basic Auth."},
        {"area": "Host firewall", "operator_action": "Allow only SSH, HTTP, HTTPS, and intentional app ports."},
        {"area": "Docker socket", "operator_action": "Keep Docker group membership limited to trusted operators."},
        {"area": "SSH hardening", "operator_action": "Use key auth, disable password login, and keep fail2ban enabled."},
        {"area": "Provider key rotation", "operator_action": "Rotate API keys at the provider after exposure or shared testing."},
        {"area": "Port bindings", "operator_action": "Change Compose bindings from the server console or a dedicated restart workflow."},
    ]


@router.get("/security/status")
def security_status(current_user: CurrentChatUser) -> dict[str, Any]:
    _require_operator(current_user)
    guardian = get_guardian_suite().auth
    operators = sorted(guardian.operator_usernames())
    env_values: dict[str, str] = {}
    for path in _managed_env_paths():
        env_values.update(_read_env_file(path))
    passphrase = env_values.get("SPARKBOT_PASSPHRASE") or os.getenv("SPARKBOT_PASSPHRASE", "")
    privileged = guardian.get_active_session(str(current_user.id))
    frontend_bind = os.getenv("SPARKBOT_FRONTEND_BIND_HOST", "").strip() or "127.0.0.1"
    frontend_port = os.getenv("SPARKBOT_FRONTEND_PORT", "").strip() or "3000"

    return {
        "generated_at": int(time.time()),
        "operator": {
            "username": current_user.username,
            "mode": "explicit" if operators else "open",
            "usernames": operators,
            "pin_configured": guardian.pin_configured(),
            "breakglass_active": privileged is not None,
            "breakglass_ttl_remaining": privileged.ttl_remaining() if privileged else 0,
        },
        "passphrase": _passphrase_score(passphrase),
        "features": {
            name: {
                "env_key": env_key,
                "enabled": os.getenv(env_key, "").strip().lower() in {"1", "true", "yes", "on"},
            }
            for name, env_key in _RISKY_FEATURE_ENV.items()
        },
        "cors": {
            "origins": settings.all_cors_origins,
            "has_wildcard": any(origin == "*" for origin in settings.all_cors_origins),
        },
        "exposure": {
            "frontend_bind_host": frontend_bind,
            "frontend_port": frontend_port,
            "frontend_public": frontend_bind in {"0.0.0.0", "::"},
            "backend_bind": "127.0.0.1:8000",
        },
        "health": {
            "backend": "ok",
            "database": "configured" if settings.SQLALCHEMY_DATABASE_URI else "unknown",
        },
        "env_files": [_file_status(path) for path in _managed_env_paths()],
        "frontend_headers": _frontend_header_status(),
        "provider_secrets": _provider_secret_status(),
        "security_modes": [
            {
                "id": "prototype",
                "label": "Prototype",
                "description": "Fast local iteration. Keep public access restricted.",
            },
            {
                "id": "private_lan",
                "label": "Private LAN",
                "description": "Explicit operators, strong passphrase, PIN configured, no public frontend.",
            },
            {
                "id": "public_internet",
                "label": "Public Internet",
                "description": "HTTPS, edge auth, explicit operators, strong secrets, headers, and locked-down ports.",
            },
        ],
        "operator_guidance": _deployment_guidance(),
    }


@router.post("/security/passphrase")
def rotate_passphrase(
    body: PassphraseUpdate,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    _require_privileged(current_user)
    score = _passphrase_score(body.passphrase)
    if score["label"] == "weak":
        raise HTTPException(status_code=400, detail="Passphrase is too weak.")
    env_path = _write_env_updates({"SPARKBOT_PASSPHRASE": body.passphrase})
    _audit(session, current_user, "passphrase_rotated", {"env_path": str(env_path), "length": len(body.passphrase)})
    return {"ok": True, "passphrase": score, "env_path": str(env_path)}


@router.post("/security/operator-users")
def set_operator_users(
    body: OperatorUsersUpdate,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    _require_privileged(current_user)
    usernames = sorted({
        item.strip().lower()
        for item in body.usernames
        if item and re.match(r"^[A-Za-z0-9_.@-]{1,100}$", item.strip())
    })
    if not usernames:
        raise HTTPException(status_code=400, detail="At least one operator username is required.")
    if (current_user.username or "").strip().lower() not in usernames:
        raise HTTPException(status_code=400, detail="The current operator must remain in the operator list.")
    env_path = _write_env_updates({"SPARKBOT_OPERATOR_USERNAMES": ",".join(usernames)})
    _audit(session, current_user, "operator_users_updated", {"env_path": str(env_path), "count": len(usernames)})
    return {"ok": True, "usernames": usernames, "env_path": str(env_path)}


@router.post("/security/operator-pin")
def set_operator_pin(
    body: OperatorPinUpdate,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    _require_operator(current_user)
    guardian = get_guardian_suite().auth
    was_configured = guardian.pin_configured()
    if was_configured:
        _require_privileged(current_user)
    try:
        guardian.set_operator_pin(
            user_id=str(current_user.id),
            current_pin=body.current_pin,
            new_pin=body.pin,
            new_pin_confirm=body.pin_confirm,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit(
        session,
        current_user,
        "operator_pin_changed" if was_configured else "operator_pin_created",
        {"changed": was_configured},
    )
    return {"ok": True, "pin_configured": True, "changed": was_configured}


@router.post("/security/features")
def set_security_features(
    body: FeatureTogglesUpdate,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    _require_privileged(current_user)
    unknown = sorted(set(body.features) - set(_RISKY_FEATURE_ENV))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported feature toggle(s): {', '.join(unknown)}")
    updates = { _RISKY_FEATURE_ENV[name]: "true" if enabled else "false" for name, enabled in body.features.items() }
    env_path = _write_env_updates(updates)
    _audit(session, current_user, "features_updated", {"env_path": str(env_path), "features": sorted(body.features)})
    return {"ok": True, "features": body.features, "restart_required": True, "env_path": str(env_path)}


@router.post("/security/fix-permissions")
def fix_env_permissions(
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    _require_privileged(current_user)
    changed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for path in _managed_env_paths():
        if not path.exists():
            skipped.append({"path": str(path), "reason": "missing"})
            continue
        if not os.access(path, os.W_OK):
            skipped.append({"path": str(path), "reason": "not writable from this runtime"})
            continue
        os.chmod(path, 0o600)
        changed.append({"path": str(path), "mode": "600"})
    _audit(session, current_user, "env_permissions_fixed", {"changed": changed, "skipped": skipped})
    return {"ok": True, "changed": changed, "skipped": skipped}
