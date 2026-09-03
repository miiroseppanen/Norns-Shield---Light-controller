from pathlib import Path

from light_console.qlc.webaccess import (
    FIELD_NAME,
    LOAD_PROJECT_PATH,
    encode_load_project,
    extract_multipart_file_payload,
    is_loading_response,
)

ROOT = Path(__file__).resolve().parents[1]
SHOW_A = ROOT / "qlc/projects/show-a.qxw"


def test_encode_matches_browser_field_and_extracts_show_a_bytes():
    xml = SHOW_A.read_bytes()
    body, content_type = encode_load_project(xml, filename="show-a.qxw")
    assert LOAD_PROJECT_PATH == "/loadProject"
    assert FIELD_NAME == "qlcprj"
    assert content_type.startswith("multipart/form-data; boundary=")
    assert f'name="{FIELD_NAME}"' in body.decode("latin1")
    extracted = extract_multipart_file_payload(body, content_type)
    assert extracted.filename == "show-a.qxw"
    assert extracted.payload == xml
    # Shield journal for this encoder: Content-Length 2267, payload 2057.
    assert len(xml) == 2057
    assert len(body) == 2267


def test_plain_body_is_accepted_as_raw_xml():
    xml = SHOW_A.read_bytes()
    extracted = extract_multipart_file_payload(xml, "application/octet-stream")
    assert extracted.payload == xml
    assert extracted.filename == ""


def test_malformed_multipart_raises():
    try:
        extract_multipart_file_payload(b"not-mime", "multipart/form-data; boundary=abc")
    except ValueError as exc:
        assert "boundary" in str(exc) or "headers" in str(exc) or "payload" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_loading_response_detects_qlc_html():
    html = (
        "<html><script>websocket.send(\"QLC+API|isProjectLoaded\");</script>"
        "Loading project...</html>"
    )
    assert is_loading_response(html) is True
    assert is_loading_response("<html>QLC+ Web Interface</html>") is False
