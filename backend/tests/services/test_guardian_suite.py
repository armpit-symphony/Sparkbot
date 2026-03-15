from app.services.guardian import get_guardian_suite, guardian_suite_inventory


def test_guardian_suite_inventory_lists_expected_components() -> None:
    inventory = guardian_suite_inventory()
    names = {item["name"] for item in inventory}

    assert names == {
        "auth",
        "executive",
        "meeting_recorder",
        "memory",
        "pending_approvals",
        "policy",
        "task_guardian",
        "token_guardian",
        "vault",
        "verifier",
    }


def test_get_guardian_suite_exposes_modules() -> None:
    suite = get_guardian_suite()

    assert suite.auth.create_pin_hash
    assert suite.policy.decide_tool_use
    assert suite.memory.memory_guardian_enabled
    assert suite.task_guardian.list_tasks
    assert suite.token_guardian.route_model
    assert suite.vault.vault_list
    assert suite.verifier.verify_task_run
