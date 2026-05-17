r"""Windows-portability regression tests for chat tools.

v1.6.81 fix: tools.py used to import the POSIX-only `pwd` module at module
load time, which broke every code path that lazy-imports tools.py on
Windows (Telegram/Discord/WhatsApp/GitHub bridges all go through
stream_chat_with_tools, which lazy-imports tools.py). The desktop launcher's
ERROR log showed the symptom on Windows installs:

    ModuleNotFoundError: No module named 'pwd'
    File "app\api\routes\chat\tools.py", line 15, in <module>

This test confirms the module imports cleanly and the only `pwd` consumer
(`_uid_name`) degrades gracefully when `pwd` is unavailable.
"""
from __future__ import annotations

import builtins
import sys


def test_tools_module_imports_without_pwd(monkeypatch) -> None:
    """tools.py must import on a platform where `pwd` is unavailable."""
    monkeypatch.delitem(sys.modules, "pwd", raising=False)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pwd":
            raise ImportError("simulated POSIX-only module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "app.api.routes.chat.tools", raising=False)

    import app.api.routes.chat.tools  # noqa: F401 — assertion is "no exception"


def test_uid_name_falls_back_to_raw_uid_without_pwd(monkeypatch) -> None:
    """_uid_name must return the raw uid string when `pwd` is unavailable
    (Windows desktop installs reach this via /proc/<pid>/status parsing in
    containerized server-ops profiles)."""
    from app.api.routes.chat import tools

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pwd":
            raise ImportError("simulated POSIX-only module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert tools._uid_name("1000") == "1000"
    assert tools._uid_name("") == "?"
    assert tools._uid_name("not-an-int") == "not-an-int"
