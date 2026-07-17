from io import StringIO

import pytest

import phonegeist


class FakeKeyboard:
    def __init__(self):
        self.events = []

    def press(self, key):
        self.events.append(("press", key))

    def release(self, key):
        self.events.append(("release", key))


@pytest.fixture(autouse=True)
def reset_state():
    with phonegeist.lock:
        phonegeist.state.update(stop=False, paused=False, running=False)
    yield
    with phonegeist.lock:
        phonegeist.state.update(stop=False, paused=False, running=False)


def test_worker_types_characters_and_normalizes_windows_newlines(monkeypatch):
    keyboard = FakeKeyboard()
    monkeypatch.setattr(phonegeist, "kb", keyboard)
    monkeypatch.setattr(phonegeist.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(phonegeist.random, "uniform", lambda _start, _end: 0)

    with phonegeist.lock:
        phonegeist.state["running"] = True
    phonegeist.do_type("A\r\n\t!", 0.02, 0)

    assert keyboard.events == [
        ("press", "A"),
        ("release", "A"),
        ("press", phonegeist.Key.enter),
        ("release", phonegeist.Key.enter),
        ("press", phonegeist.Key.tab),
        ("release", phonegeist.Key.tab),
        ("press", "!"),
        ("release", "!"),
    ]
    assert phonegeist.state["running"] is False


def test_home_and_status_routes():
    client = phonegeist.app.test_client()

    page = client.get("/")
    assert page.status_code == 200
    assert b"Send to laptop" in page.data
    assert client.get("/status").get_json() == {
        "paused": False,
        "running": False,
    }


def test_type_rejects_invalid_input():
    client = phonegeist.app.test_client()

    assert client.post("/type", json={}).status_code == 400
    assert client.post("/type", json={"text": 123}).status_code == 400
    assert client.post("/type", json={"text": "x", "speed": "nope"}).status_code == 400
    assert client.post("/type", json={"text": "x" * 100_001}).status_code == 413


def test_type_prevents_overlapping_jobs():
    client = phonegeist.app.test_client()
    with phonegeist.lock:
        phonegeist.state["running"] = True

    response = client.post("/type", json={"text": "hello"})

    assert response.status_code == 409
    assert response.get_json()["error"] == "already typing"


def test_qr_output_is_generated():
    output = StringIO()
    phonegeist.print_qr("http://192.168.1.10:5000", output)

    assert len(output.getvalue().splitlines()) > 10


def test_cli_prints_url_and_starts_server(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(phonegeist, "find_lan_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(phonegeist, "print_qr", lambda url: calls.update(qr=url))
    monkeypatch.setattr(
        phonegeist.app,
        "run",
        lambda **kwargs: calls.update(server=kwargs),
    )

    phonegeist.main(["--port", "5050"])

    assert calls["qr"] == "http://192.168.1.10:5050"
    assert calls["server"]["host"] == "0.0.0.0"
    assert calls["server"]["port"] == 5050
    assert "http://192.168.1.10:5050" in capsys.readouterr().out
