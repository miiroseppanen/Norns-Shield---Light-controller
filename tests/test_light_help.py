from pathlib import Path
import subprocess

from light_console.version import VERSION

ROOT = Path(__file__).resolve().parents[1]
HELP = ROOT / "packaging/light-help"
WRAPPER = ROOT / "packaging/light-help.wrapper"
PROFILE = ROOT / "packaging/profile.d/light-help.sh"
INSTALL = ROOT / "packaging/install-light-help.sh"
VERSION_PY = ROOT / "light_console/version.py"

STARTUP_SHOW = "qlc/projects/siirtyma-startup-wiz16-halloween-uv.qxw"
RSYNC_EXCLUDES = (
    "--exclude '.venv'",
    "--exclude '.git'",
    "--exclude '__pycache__'",
    "--exclude '.pytest_cache'",
    "--exclude '*.pyc'",
    "--exclude '.cursor'",
    "--exclude '.impeccable/config.local.json'",
)
BOX_BLOCK = set("─│┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬█▄▀▌▐■□▪▫●○")
CANONICAL_WORDMARK = (
    "//      //  ////  // // /////     ////  ///// ////\n"
    "//      // //     // //   //     //      //   // //\n"
    "//      // // //  /////   //     //      //   ////\n"
    "//      // //  // // //   //     //      //   // //\n"
    "//////  //  ////  // //   //      ////   //   //  //"
)


def _help_output() -> str:
    return subprocess.check_output([HELP], text=True)


def _continuation_block(lines: list[str], start: str) -> str:
    body: list[str] = []
    taking = False
    for line in lines:
        if not taking:
            if start in line:
                taking = True
                body.append(line.lstrip())
            continue
        body.append(line)
        if not line.rstrip().endswith("\\"):
            break
    assert body, start
    return "\n".join(body) + "\n"


def test_light_help_prints_compact_guide():
    out = _help_output()
    lines = out.splitlines()
    assert 40 <= len(lines) <= 60
    assert max(len(line) for line in lines) <= 78
    for line in lines:
        assert len(line) <= 78, line
    assert all(ord(ch) < 128 for ch in out)
    assert VERSION in out
    for needle in (
        "systemctl status light-console --no-pager",
        "systemctl status qlcplus --no-pager",
        "systemctl status wizbridge --no-pager",
        "systemctl status shieldxl-wiz-isolation --no-pager",
        "nmcli device status",
        "sudo systemctl restart light-console",
        "sudo systemctl restart qlcplus",
        "journalctl -u light-console -n 80 --no-pager",
        "journalctl -u qlcplus -n 80 --no-pager",
        "journalctl -u wizbridge -n 80 --no-pager",
        "http://shieldxl-light.local:9999",
        "/home/light/shows/master.qxw",
        "LIGHT-CONTROL",
        "192.168.88.246",
        "WIZ-LIGHTS AP",
        "10.42.0.1",
        "WIZ -> CONTROL / DEVICES",
        "cd /Users/miiroseppanen/shieldxl-light-console && rsync -az",
        "light@shieldxl-light.local:~/light-console/",
        "./scripts/import-production-workspace.sh --install",
        "never copy onto /home/light/shows/master.qxw",
        "OLED SYSTEM -> SHUTDOWN -> K3",
        "sudo /usr/sbin/shutdown -h now",
        "192.168.88.248 -- DO NOT CONTACT",
        "light-help",
    ):
        assert needle in out, needle
    for extra in RSYNC_EXCLUDES:
        assert extra in out, extra

    assert "CLIENT" not in out
    assert "git pull" not in out
    assert "nmcli connection up" not in out
    assert "nmcli connection down" not in out
    assert "light-console-wiz" not in out
    assert "scp " not in out
    assert "Milestone" not in out
    assert "Refresh 2D" not in out
    assert "current.qxw" not in out
    assert "password" not in out.lower()
    assert "CONFIRM" not in out
    assert "SYSTEM -> SHUTDOWN -> CONFIRM" not in out
    assert "valot.local" not in out
    assert "disabled" not in out.lower()
    assert "not configured" not in out.lower()
    assert "import-show.sh" not in out
    assert "SHIELD XL LIGHT CONSOLE" not in out


def test_wordmark_is_canonical_locked_block():
    out = _help_output()
    mark = out.splitlines()[:5]
    assert "\n".join(mark) == CANONICAL_WORDMARK
    assert len(mark) == 5
    assert max(len(line) for line in mark) <= 65
    text = "\n".join(mark)
    assert "#" not in text
    assert "\\" not in text
    assert "|" not in text
    assert "_" not in text
    assert "-" not in text
    assert all(ord(ch) < 128 for ch in text)
    assert not (set(text) & BOX_BLOCK)
    assert set(text) - {"\n"} <= set("/ ")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert CANONICAL_WORDMARK in readme
    assert not HELP.read_text().split("cat <<'EOF'", 1)[1].startswith("##")


def test_version_comes_from_canonical_source():
    source = HELP.read_text()
    assert VERSION not in source
    assert "light_console/version.py" in source
    assert VERSION_PY.read_text().split("VERSION = ", 1)[1].split("\n", 1)[0].strip() == f'"{VERSION}"'
    assert _help_output().splitlines()[5] == VERSION


def test_wrapped_commands_remain_valid_shell():
    lines = _help_output().splitlines()
    rsync = _continuation_block(lines, "cd /Users/miiroseppanen/shieldxl-light-console && rsync -az")
    show = _continuation_block(lines, "./scripts/import-production-workspace.sh --install")
    subprocess.check_call(["bash", "-n", "-c", rsync])
    subprocess.check_call(["bash", "-n", "-c", show])
    echoed = subprocess.check_output(
        ["bash", "-c", show.replace("./scripts/import-production-workspace.sh --install", "printf '%s\\n'")],
        text=True,
    ).strip()
    assert echoed == STARTUP_SHOW
    assert "scp " not in show
    assert "master.qxw" not in show


def test_login_hook_is_quiet():
    text = PROFILE.read_text()
    assert "SSH_CONNECTION" in text
    assert "PS1" in text
    assert "LIGHT_HELP_SHOWN" in text
    assert "[ -t 1 ]" in text
    assert "/usr/local/bin/light-help" in text
    for banned in ("systemctl", "journalctl", "ping", "curl", "nmcli", "restart"):
        assert banned not in text


def test_wrapper_follows_deployed_tree():
    text = WRAPPER.read_text()
    assert "/home/light/light-console/packaging/light-help" in text
    assert "exec" in text
    assert "192.168.88.248" not in text


def test_installer_is_reproducible_and_side_effect_free():
    text = INSTALL.read_text()
    assert 'HELP_DST="/usr/local/bin/light-help"' in text
    assert 'WRAP_SRC="$ROOT/packaging/light-help.wrapper"' in text
    assert 'PROFILE_DST="/etc/profile.d/light-help.sh"' in text
    assert 'CHECK_DST="/usr/local/bin/light-appliance-check"' in text
    assert 'SHOWS_DIR="/home/light/shows"' in text
    assert "current.qxw" in text
    assert 'install -m 755 -o root -g root "$WRAP_SRC" "$HELP_DST"' in text
    assert "systemctl" not in text
    assert "reboot" not in text
    appliance = (ROOT / "packaging/install-appliance.sh").read_text()
    assert 'bash "$ROOT/packaging/install-light-help.sh"' in appliance
