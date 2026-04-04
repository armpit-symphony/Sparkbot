# Runtime hook: register tiktoken encoding plugins before any app code runs.
#
# tiktoken >= 0.8 discovers encodings via importlib.metadata entry points
# (group "tiktoken_ext").  In a frozen PyInstaller bundle the dist-info
# directories are absent, so importlib.metadata finds nothing and every
# encoding lookup raises "Unknown encoding <name>. Plugins found: []".
#
# This hook manually imports tiktoken_ext.openai_public (which defines
# cl100k_base, p50k_base, r50k_base, o200k_base, etc.) and registers it
# with tiktoken's internal registry, replicating what the entry-point
# discovery would have done at runtime.
import sys

if getattr(sys, "frozen", False):
    try:
        import tiktoken_ext.openai_public  # noqa: F401
        from tiktoken.registry import _registry  # type: ignore[attr-defined]
        import tiktoken_ext.openai_public as _oai

        for _name in dir(_oai):
            _val = getattr(_oai, _name)
            if callable(_val) and not _name.startswith("_"):
                try:
                    _enc = _val()
                    if hasattr(_enc, "name") and _enc.name not in _registry:
                        _registry[_enc.name] = _val
                except Exception:
                    pass
    except Exception:
        # Non-fatal: litellm will fall back to character-based token estimation
        pass
