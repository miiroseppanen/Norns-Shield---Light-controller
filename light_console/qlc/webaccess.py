"""QLC+ 5.2.2 WebAccess /loadProject framing.

Verified on Shield qlcplus-qml 5.2.2: the browser Load project control is a
native HTML form POST, not a WebSocket command and not a server filesystem path.

    POST /loadProject
    Content-Type: multipart/form-data
    field name: qlcprj
    body: the .qxw file bytes

QLC extractMultipartFilePayload() (webaccessbase.cpp) pulls the first MIME part.
A non-multipart body is accepted as the raw XML (programmatic shortcut).

Do not call this against a live offscreen QML engine from Light Console yet:
show-a.qxw ingested (payload size matched the file) then QML Virtual Console
refresh wedged HTTP :9999. See research/phase-06-show-project-ui.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_BOUNDARY = "----LightConsoleFormBoundary7MA4YWxkTrZu0gW"
LOAD_PROJECT_PATH = "/loadProject"
FIELD_NAME = "qlcprj"

_FILENAME = re.compile(r'filename="([^"]*)"')


@dataclass(frozen=True)
class MultipartFile:
    filename: str
    payload: bytes


def encode_load_project(
    xml: bytes,
    *,
    filename: str = "show.qxw",
    boundary: str = DEFAULT_BOUNDARY,
) -> tuple[bytes, str]:
    """Return (body, Content-Type) matching the WebAccess load form."""
    if not xml:
        raise ValueError("empty workspace")
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{FIELD_NAME}"; '
        f'filename="{safe_name}"\r\n'
        "Content-Type: application/octet-stream\r\n"
        "\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + xml + footer
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def extract_multipart_file_payload(
    body: bytes,
    content_type: str,
) -> MultipartFile:
    """Mirror QLC 5.2.2 extractMultipartFilePayload()."""
    if not body:
        raise ValueError("empty body")
    ctype = content_type or ""
    is_multipart = "multipart/form-data" in ctype.lower()
    boundary_at = ctype.lower().find("boundary=")
    if not is_multipart or boundary_at < 0:
        return MultipartFile(filename="", payload=body)

    boundary = ctype[boundary_at + 9 :].strip()
    if ";" in boundary:
        boundary = boundary.split(";", 1)[0].strip()
    if len(boundary) >= 2 and boundary[0] == '"' and boundary[-1] == '"':
        boundary = boundary[1:-1]
    if not boundary:
        raise ValueError("missing multipart boundary")

    marker = b"--" + boundary.encode("utf-8")
    part_start = body.find(marker)
    if part_start < 0:
        raise ValueError("multipart boundary not found")
    part_start += len(marker)
    if body[part_start : part_start + 2] == b"\r\n":
        part_start += 2
    elif part_start < len(body) and body[part_start : part_start + 1] == b"\n":
        part_start += 1

    headers_end = body.find(b"\r\n\r\n", part_start)
    sep = 4
    if headers_end < 0:
        headers_end = body.find(b"\n\n", part_start)
        sep = 2
    if headers_end < 0:
        raise ValueError("multipart headers not found")

    part_headers = body[part_start:headers_end].decode("utf-8", "replace")
    match = _FILENAME.search(part_headers)
    filename = match.group(1) if match else ""

    payload_start = headers_end + sep
    payload_end = body.find(b"\r\n" + marker, payload_start)
    if payload_end < 0:
        payload_end = body.find(b"\n" + marker, payload_start)
    if payload_end < 0:
        raise ValueError("multipart payload end not found")
    return MultipartFile(filename=filename, payload=body[payload_start:payload_end])


def is_loading_response(html: str) -> bool:
    return "Loading project..." in html or "isProjectLoaded" in html
