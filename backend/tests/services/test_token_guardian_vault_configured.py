from app.services.guardian import token_guardian


def test_token_guardian_treats_vault_keys_as_configured(monkeypatch) -> None:
    """Minimal vault wiring proof: routing eligibility should consider vault metadata."""
    monkeypatch.setenv("SPARKBOT_TOKEN_GUARDIAN_MODE", "live")

    # Ensure env vars are absent so only vault metadata can satisfy "configured".
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Patch module-level helper so vault-backed metadata counts as configured.
    import app.services.guardian.token_guardian as tg

    monkeypatch.setattr(
        tg,
        "_env_or_vault_has",
        lambda env, alias: env == "OPENAI_API_KEY" and alias == "api_key_openai",
    )

    assert token_guardian._model_is_configured("gpt-4o-mini") is True
