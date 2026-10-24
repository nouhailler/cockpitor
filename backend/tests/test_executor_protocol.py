"""Protocol tests only: these do not qualify a privileged executor or real engines."""

import json

import pytest
from app.actions import ActionRequest
from app.executor_protocol import MAX_TICKETS, ExecutorPolicy, ProtocolRejected
from pydantic import ValidationError


@pytest.fixture
def protocol():
    now = [10.0]
    policy = ExecutorPolicy(
        1000, frozenset({("service.restart", "fixture.service", None)}), lambda: now[0]
    )
    request = ActionRequest(action="service.restart", target="fixture.service")
    snapshot = {"state": "active", "configuration_fingerprint": "a" * 64}
    operation = "b" * 32
    ticket = policy.issue(1000, operation, request, snapshot)
    frame = json.dumps({"version": 1, "operation_id": operation, "ticket": ticket}).encode()
    return policy, now, request, snapshot, operation, frame


def test_exact_intent_and_replay(protocol):
    policy, _, request, snapshot, operation, frame = protocol
    result = policy.consume(1000, frame, snapshot)
    assert (result.action, result.target, result.engine) == (
        "service.restart",
        "fixture.service",
        None,
    )
    with pytest.raises(ProtocolRejected):
        policy.consume(1000, frame, snapshot)
    with pytest.raises(ProtocolRejected):
        policy.issue(1000, operation, request, snapshot)


@pytest.mark.parametrize("uid", [0, 1001, True, "1000"])
def test_peer_cannot_be_supplied_in_payload_or_coerced(protocol, uid):
    policy, _, _, snapshot, _, frame = protocol
    with pytest.raises(ProtocolRejected):
        policy.consume(uid, frame, snapshot)
    assert policy.consume(1000, frame, snapshot)


@pytest.mark.parametrize("change", ["expiry", "state", "configuration", "ticket"])
def test_failed_checks_burn_ticket(protocol, change):
    policy, now, _, snapshot, _, frame = protocol
    updated = dict(snapshot)
    if change == "expiry":
        now[0] += 30
    elif change == "ticket":
        payload = json.loads(frame)
        payload["ticket"] = "0" * 64
        frame = json.dumps(payload).encode()
    else:
        updated["state" if change == "state" else "configuration_fingerprint"] = "changed"
    with pytest.raises(ProtocolRejected):
        policy.consume(1000, frame, updated)
    with pytest.raises(ProtocolRejected):
        policy.consume(1000, frame, snapshot)


@pytest.mark.parametrize(
    "frame",
    [
        b"",
        b"x" * 2049,
        b"\xff",
        b"[]",
        b"null",
        b'{"version":1,"version":1}',
        b'{"version":true}',
        b'{"command":"sudo reboot"}',
    ],
)
def test_malformed_frames(protocol, frame):
    policy, _, _, snapshot, _, _ = protocol
    with pytest.raises(ProtocolRejected):
        policy.consume(1000, frame, snapshot)


def test_positive_grants_only(protocol):
    policy, _, _, snapshot, _, _ = protocol
    for action, target in [
        ("service.stop", "fixture.service"),
        ("service.restart", "other.service"),
    ]:
        with pytest.raises(ProtocolRejected):
            policy.issue(1000, "c" * 32, ActionRequest(action=action, target=target), snapshot)
    assert not ExecutorPolicy(1000, frozenset()).grants
    with pytest.raises((ValueError, ValidationError)):
        ExecutorPolicy(1000, frozenset({("service.restart", "ssh.service", None)}))


def test_restart_invalidates_tickets(protocol):
    _, _, _, snapshot, _, frame = protocol
    replacement = ExecutorPolicy(1000, frozenset({("service.restart", "fixture.service", None)}))
    with pytest.raises(ProtocolRejected):
        replacement.consume(1000, frame, snapshot)


def test_capacity_never_evicts_used_ids(protocol):
    policy, _, request, snapshot, _, frame = protocol
    policy.consume(1000, frame, snapshot)
    for i in range(MAX_TICKETS - 1):
        policy.issue(1000, f"{i:032x}", request, snapshot)
    with pytest.raises(ProtocolRejected):
        policy.issue(1000, "f" * 32, request, snapshot)
    assert len(policy.reserved) == MAX_TICKETS


@pytest.mark.parametrize(
    "field,value", [("version", True), ("version", 2), ("peer_uid", 1000), ("command", "reboot")]
)
def test_envelope_strictness(protocol, field, value):
    policy, _, _, snapshot, _, frame = protocol
    payload = json.loads(frame)
    payload[field] = value
    with pytest.raises(ProtocolRejected):
        policy.consume(1000, json.dumps(payload).encode(), snapshot)
    assert policy.consume(1000, frame, snapshot)
