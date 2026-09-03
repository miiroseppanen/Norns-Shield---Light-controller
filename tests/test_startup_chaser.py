from light_console.startup_chaser import run_once


class FakeTransport:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.sent: list[str] = []

    def send_text(self, text: str) -> None:
        self.sent.append(text)

    def recv_text(self) -> str | None:
        if not self.replies:
            return None
        return self.replies.pop(0)


def test_startup_skips_start_when_already_running(tmp_path, monkeypatch):
    monkeypatch.setattr("light_console.startup_chaser.STATUS_PATH", tmp_path / "st")
    fake = FakeTransport(
        [
            "QLC+API|getFunctionsList|0|startup|1|Warm",
            "VC_PAGE|1",
            "QLC+API|getFunctionType|Chaser",
            "QLC+API|getFunctionStatus|Running",
        ]
    )
    assert run_once(fake, settle=lambda _: None) == "RUNNING"
    assert not any("setFunctionStatus" in msg for msg in fake.sent)


def test_startup_starts_when_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr("light_console.startup_chaser.STATUS_PATH", tmp_path / "st")
    fake = FakeTransport(
        [
            "QLC+API|getFunctionsList|0|startup",
            "VC_PAGE|1",
            "QLC+API|getFunctionType|Chaser",
            "QLC+API|getFunctionStatus|Stopped",
            "QLC+API|getFunctionStatus|Running",
        ]
    )
    assert run_once(fake, settle=lambda _: None) == "RUNNING"
    assert "QLC+API|setFunctionStatus|0|1" in fake.sent
    assert "status=RUNNING" in (tmp_path / "st").read_text()
