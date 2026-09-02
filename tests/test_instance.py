from pathlib import Path

from light_console.instance import InstanceLock, InstanceLockHeld


def test_second_lock_fails(tmp_path: Path):
    path = tmp_path / "instance.lock"
    a = InstanceLock(path)
    b = InstanceLock(path)
    a.acquire()
    try:
        try:
            b.acquire()
            raise AssertionError("second lock must fail")
        except InstanceLockHeld:
            pass
    finally:
        a.close()
    b.acquire()
    b.close()


def test_lock_releases(tmp_path: Path):
    path = tmp_path / "instance.lock"
    a = InstanceLock(path)
    a.acquire()
    a.close()
    c = InstanceLock(path)
    c.acquire()
    c.close()
