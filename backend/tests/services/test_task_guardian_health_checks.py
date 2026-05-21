import asyncio

from app.services.guardian import health_checks


class _Metrics:
    def __init__(self, *, percent=0.0, available=0, free=0, total=0):
        self.percent = percent
        self.available = available
        self.free = free
        self.total = total


class _FakePsutil:
    @staticmethod
    def boot_time():
        return 1_700_000_000.0

    @staticmethod
    def cpu_percent(interval=0.0):
        return 12.0

    @staticmethod
    def virtual_memory():
        return _Metrics(percent=35.0, available=8_000_000_000, total=16_000_000_000)

    @staticmethod
    def swap_memory():
        return _Metrics(percent=0.0, total=0)

    @staticmethod
    def disk_usage(_path):
        return _Metrics(percent=42.0, free=120_000_000_000, total=240_000_000_000)

    @staticmethod
    def sensors_battery():
        return None


class _CriticalPsutil(_FakePsutil):
    @staticmethod
    def cpu_percent(interval=0.0):
        return 96.0

    @staticmethod
    def virtual_memory():
        return _Metrics(percent=96.0, available=500_000_000, total=16_000_000_000)

    @staticmethod
    def disk_usage(_path):
        return _Metrics(percent=93.0, free=4_000_000_000, total=80_000_000_000)


async def _fake_local_ai_status(**kwargs):
    kwargs["system"]["local_ai"] = "setup optional"
    kwargs["passed"].append("Local AI status check skipped in test.")


def _fake_connector_status(**kwargs):
    kwargs["system"]["connectors"] = "0 configured, setup optional"


def test_health_templates_are_disabled_and_app_only() -> None:
    templates = health_checks.health_task_templates()
    ids = {template["id"] for template in templates}

    assert ids == {"pc_health_check", "server_health_check"}
    assert all(template["tool_name"] == health_checks.HEALTH_CHECK_TOOL_NAME for template in templates)
    assert all(template["schedule"] == "daily-local:06:00" for template in templates)
    assert all(template["enabled"] is False for template in templates)
    assert all(template["delivery_channels"] == ["app"] for template in templates)


def test_health_collector_reports_nominal_without_destructive_actions(monkeypatch) -> None:
    monkeypatch.setattr(health_checks, "_psutil", lambda: _FakePsutil)
    monkeypatch.setattr(health_checks, "_collect_local_ai_status", _fake_local_ai_status)
    monkeypatch.setattr(health_checks, "_collect_connector_status", _fake_connector_status)

    payload = asyncio.run(health_checks.collect_health(mode="pc"))
    report = health_checks.render_health_report(payload)

    assert payload["status"] == "Nominal"
    assert payload["read_only"] is True
    assert "SEV-1 Assessment:\nNONE" in report
    assert "No action required." in report
    assert "no packages were updated" in report
    assert "secret" not in report.lower()


def test_health_collector_classifies_critical_disk_and_memory(monkeypatch) -> None:
    monkeypatch.setattr(health_checks, "_psutil", lambda: _CriticalPsutil)
    monkeypatch.setattr(health_checks, "_collect_local_ai_status", _fake_local_ai_status)
    monkeypatch.setattr(health_checks, "_collect_connector_status", _fake_connector_status)

    payload = asyncio.run(health_checks.collect_health(mode="server"))
    report = health_checks.render_health_report(payload)

    assert payload["status"] == "Critical"
    assert payload["sev1_detected"] is True
    assert "SEV-1 Assessment:\nDETECTED" in report
    assert "Disk" in report
    assert "Memory" in report


def test_health_report_delivery_channels_are_sanitized() -> None:
    channels = health_checks.delivery_channels_from_args(
        {"delivery_channels": ["app", "telegram", "bad", "slack", "telegram"]}
    )

    assert channels == ["app", "telegram", "slack"]


def test_health_report_delivery_channels_read_structured_preferences() -> None:
    channels = health_checks.delivery_channels_from_args(
        {
            "delivery": {
                "channels": [
                    {"channel": "app", "enabled": True},
                    {"channel": "telegram", "enabled": True},
                    {"channel": "discord", "enabled": False},
                    {"channel": "whatsapp", "enabled": True},
                    {"channel": "sms", "enabled": True},
                ]
            }
        }
    )

    assert channels == ["app", "telegram", "whatsapp", "sms"]


def test_health_delivery_preferences_mark_sms_future_without_secrets(monkeypatch) -> None:
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    preferences = health_checks.delivery_preferences_from_args(
        {
            "delivery_channels": ["app", "sms", "slack"],
            "slack_channel": "C-test",
            "slack_token": "should-not-appear",
        }
    )

    by_channel = {item["channel"]: item for item in preferences["channels"]}
    assert by_channel["app"]["configured"] is True
    assert by_channel["sms"]["configured"] is False
    assert by_channel["sms"]["status"] == "setup_needed"
    assert "not implemented" in by_channel["sms"]["setup_message"]
    assert by_channel["slack"]["configured"] is False
    assert by_channel["slack"]["target_label"] == "C-test"
    assert by_channel["sms"]["target_label"] == ""
    assert "should-not-appear" not in str(preferences)
