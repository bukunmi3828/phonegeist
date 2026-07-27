from io import StringIO
from io import BytesIO

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
    original_receive_dir = phonegeist.RECEIVED_DIR
    original_share_dir = phonegeist.SHARE_DIR
    with phonegeist.lock:
        phonegeist.state.update(stop=False, paused=False, running=False)
    yield
    phonegeist.RECEIVED_DIR = original_receive_dir
    phonegeist.SHARE_DIR = original_share_dir
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
    assert b"Send photos to computer" in page.data
    assert b"Download from computer" in page.data
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


def test_upload_saves_multiple_photos(tmp_path, monkeypatch):
    monkeypatch.setattr(phonegeist, "RECEIVED_DIR", tmp_path)
    client = phonegeist.app.test_client()

    response = client.post("/upload", data={
        "photos": [
            (BytesIO(b"first"), "camera/photo one.jpg"),
            (BytesIO(b"second"), "other.png"),
        ]
    }, content_type="multipart/form-data")

    assert response.status_code == 200
    assert response.get_json()["saved"] == 2
    assert sorted(path.read_bytes() for path in tmp_path.iterdir()) == [b"first", b"second"]


def test_upload_rejects_missing_and_non_image_files(tmp_path, monkeypatch):
    monkeypatch.setattr(phonegeist, "RECEIVED_DIR", tmp_path)
    client = phonegeist.app.test_client()

    assert client.post("/upload", data={}).status_code == 400
    response = client.post("/upload", data={
        "photos": (BytesIO(b"not an image"), "notes.exe")
    }, content_type="multipart/form-data")
    assert response.status_code == 415
    assert list(tmp_path.iterdir()) == []


def test_downloads_list_and_send_shared_files(tmp_path, monkeypatch):
    monkeypatch.setattr(phonegeist, "SHARE_DIR", tmp_path)
    (tmp_path / "report.pdf").write_bytes(b"pdf data")
    (tmp_path / "photo.jpg").write_bytes(b"jpg data")
    (tmp_path / "nested").mkdir()
    client = phonegeist.app.test_client()

    response = client.get("/downloads")

    assert response.status_code == 200
    assert response.get_json()["files"] == [
        {"name": "photo.jpg", "size": 8},
        {"name": "report.pdf", "size": 8},
    ]
    download = client.get("/download/report.pdf")
    assert download.status_code == 200
    assert download.data == b"pdf data"


def test_download_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(phonegeist, "SHARE_DIR", tmp_path)
    client = phonegeist.app.test_client()

    assert client.get("/download/../secret.txt").status_code == 400


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


def test_cli_can_set_photo_destination(monkeypatch, tmp_path, capsys):
    calls = {}
    monkeypatch.setattr(phonegeist, "find_lan_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(phonegeist, "print_qr", lambda _url: None)
    monkeypatch.setattr(phonegeist.app, "run", lambda **kwargs: calls.update(kwargs))

    phonegeist.main(["--receive-dir", str(tmp_path)])

    assert phonegeist.RECEIVED_DIR == tmp_path.resolve()
    assert str(tmp_path.resolve()) in capsys.readouterr().out
    assert calls["host"] == "0.0.0.0"


def test_cli_can_set_share_directory(monkeypatch, tmp_path, capsys):
    calls = {}
    monkeypatch.setattr(phonegeist, "find_lan_ip", lambda: "192.168.1.10")
    monkeypatch.setattr(phonegeist, "print_qr", lambda _url: None)
    monkeypatch.setattr(phonegeist.app, "run", lambda **kwargs: calls.update(kwargs))

    phonegeist.main(["--share-dir", str(tmp_path)])

    assert phonegeist.SHARE_DIR == tmp_path.resolve()
    assert str(tmp_path.resolve()) in capsys.readouterr().out
    assert calls["host"] == "0.0.0.0"
