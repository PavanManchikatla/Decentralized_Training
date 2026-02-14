import pytest
from pydantic import ValidationError

from models import NodePolicy, RolePreference, TaskType


def test_node_policy_valid_range() -> None:
    policy = NodePolicy(
        enabled=True,
        cpu_cap_percent=80,
        gpu_cap_percent=60,
        ram_cap_percent=70,
        task_allowlist=[TaskType.INFERENCE, TaskType.EMBEDDINGS],
        role_preference=RolePreference.PREFER_INFERENCE,
    )

    assert policy.cpu_cap_percent == 80
    assert policy.gpu_cap_percent == 60
    assert policy.role_preference == RolePreference.PREFER_INFERENCE


def test_node_policy_rejects_out_of_range_cpu_cap() -> None:
    with pytest.raises(ValidationError):
        NodePolicy(
            enabled=True,
            cpu_cap_percent=101,
            ram_cap_percent=50,
            task_allowlist=[TaskType.INFERENCE],
            role_preference=RolePreference.AUTO,
        )


def test_node_policy_defaults_role_preference() -> None:
    policy = NodePolicy(
        enabled=True,
        cpu_cap_percent=100,
        ram_cap_percent=100,
        task_allowlist=[TaskType.PREPROCESS],
    )

    assert policy.role_preference == RolePreference.AUTO
