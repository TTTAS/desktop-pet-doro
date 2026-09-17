import json
import threading

import pytest

pytest.importorskip("websockets")
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

from doro_app.core.presence.bridge import PresenceBridge


@pytest.fixture
def bridge():
    events = []
    received = threading.Event()

    def on_page(page):
        events.append(page)
        if page:
            received.set()

    bridge = PresenceBridge("a" * 32, "T" * 43, on_page, port=0)
    bridge.start()
    yield bridge, events, received
    bridge.shutdown()


def test_paired_client_page_and_clear(bridge):
    server, _events, received = bridge
    with connect(
        f"ws://127.0.0.1:{server.port}/presence",
        origin=server.origin,
        subprotocols=["doro-v1", "auth." + "T" * 43],
        proxy=None,
    ) as ws:
        ws.send(
            json.dumps(
                {
                    "type": "page",
                    "focused": True,
                    "visible": True,
                    "tab_id": 1,
                    "url": "https://example.test",
                    "title": "A",
                    "text": "content",
                }
            )
        )
        assert received.wait(2)
        assert server.current_page.text == "content"
        ws.send('{"type":"clear"}')
        ws.send('{"type":"ping"}')
        assert json.loads(ws.recv(timeout=2))["type"] == "pong"
        assert server.current_page is None


@pytest.mark.parametrize(
    "origin,token",
    [
        ("https://evil.example", "T" * 43),
        ("chrome-extension://" + "a" * 32, "X" * 43),
        (None, "T" * 43),
    ],
)
def test_bad_pairing_is_403(bridge, origin, token):
    server, _, _ = bridge
    with pytest.raises(InvalidStatus) as error:
        connect(
            f"ws://127.0.0.1:{server.port}/presence",
            origin=origin,
            subprotocols=["doro-v1", "auth." + token],
            proxy=None,
        )
    assert error.value.response.status_code == 403
