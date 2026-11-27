from __future__ import annotations

import json
from unittest.mock import MagicMock

from pi.client import ServerClient


def _response(data):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(data).encode("utf-8")
    return response


def test_passage_uses_backend_contract_and_persists_until_accepted(tmp_path, monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return _response({"accepted": 1, "count_today": 7, "pending_commands": []})

    monkeypatch.setattr("pi.client.urllib.request.urlopen", urlopen)
    queue_path = tmp_path / "pending.jsonl"
    client = ServerClient(
        base_url="http://localhost:8000/",
        api_key="unit-test-key",
        queue_path=str(queue_path),
    )
    event = client.send_event(total=7, ts=0, min_distance_cm=42.5)

    assert event["event_id"]
    assert client.pending == 1
    assert client._flush_events() is True
    request = seen["request"]
    assert request.full_url == "http://localhost:8000/api/v1/passages"
    assert request.get_header("X-api-key") == "unit-test-key"
    payload = json.loads(request.data)
    assert payload["events"] == [event]
    assert client.pending == 0
    assert client.server_count == 7
    assert queue_path.read_text(encoding="utf-8") == ""


def test_commands_are_deduplicated_and_ack_uses_device_endpoint(tmp_path, monkeypatch):
    responses = [
        _response([{"id": 12, "command": "reset_counter", "payload": {}, "status": "sent"}]),
        _response([{"id": 12, "command": "reset_counter", "payload": {}, "status": "sent"}]),
        _response({"id": 12, "status": "success"}),
    ]
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        return responses.pop(0)

    monkeypatch.setattr("pi.client.urllib.request.urlopen", urlopen)
    client = ServerClient(base_url="http://localhost:8000", api_key="key", queue_path=str(tmp_path / "q"))
    assert client._poll_commands()
    assert client._poll_commands()
    commands = client.consume_commands()
    assert [c["id"] for c in commands] == [12]
    assert client.server_count == 0

    client._acks.append({"id": 12, "status": "success", "detail": "LCD reset"})
    assert client._flush_acks()
    assert requests[-1].full_url.endswith("/api/v1/device/commands/12/ack")
    assert json.loads(requests[-1].data) == {"status": "success", "detail": "LCD reset"}
