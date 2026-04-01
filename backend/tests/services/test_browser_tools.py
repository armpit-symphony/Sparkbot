from app.api.routes.chat.tools import _normalize_browser_url


def test_normalize_browser_url_adds_https_scheme() -> None:
    normalized, err = _normalize_browser_url("example.com")
    assert err is None
    assert normalized == "https://example.com/"


def test_normalize_browser_url_blocks_localhost_by_default() -> None:
    normalized, err = _normalize_browser_url("http://localhost:3000")
    assert normalized is None
    assert err is not None
    assert "blocked" in err


def test_normalize_browser_url_allows_localhost_when_explicitly_enabled() -> None:
    normalized, err = _normalize_browser_url(
        "http://localhost:3000",
        allow_private_network=True,
    )
    assert err is None
    assert normalized == "http://localhost:3000/"


def test_normalize_browser_url_blocks_private_ip_by_default() -> None:
    normalized, err = _normalize_browser_url("http://192.168.1.10")
    assert normalized is None
    assert err is not None
    assert "private" in err


def test_normalize_browser_url_rejects_non_http_scheme() -> None:
    normalized, err = _normalize_browser_url("ftp://example.com")
    assert normalized is None
    assert err is not None
    assert "http://" in err
