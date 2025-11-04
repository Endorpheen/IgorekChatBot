from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.settings import Settings
from app.webui import register_webui


@pytest.fixture
def webui_setup(tmp_path: Path) -> Dict[str, Path]:
    root = tmp_path / "webui"
    root.mkdir()

    (root / "index.html").write_text("<html>home</html>", encoding="utf-8")
    (root / "asset.bin").write_bytes(b"0123456789")
    (root / "nested").mkdir()
    (root / "nested" / "note.txt").write_text("nested note", encoding="utf-8")

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    symlink = root / "leak.txt"
    try:
        os.symlink(outside, symlink)
        symlink_valid = True
    except OSError:
        symlink_valid = False

    return {
        "root": root,
        "outside": outside,
        "symlink": symlink if symlink_valid else None,
    }


@pytest.fixture
def webui_client(webui_setup: Dict[str, Path]) -> Tuple[TestClient, Dict[str, Path]]:
    app = FastAPI()
    settings = Settings(webui_dir=webui_setup["root"])
    register_webui(app, settings)
    app.mount("/web-static", StaticFiles(directory=str(webui_setup["root"]), html=True), name="web-static")
    return TestClient(app), webui_setup


def test_staticfiles_matches_manual_behavior(webui_client: Tuple[TestClient, Dict[str, Path]]) -> None:
    client, _ = webui_client

    assert client.get("/web-ui/index.html").content == client.get("/web-static/index.html").content

    resp_ui = client.get("/web-ui/missing.txt")
    resp_static = client.get("/web-static/missing.txt")
    assert resp_ui.status_code == resp_static.status_code == 404

    range_headers = {"Range": "bytes=0-3"}
    resp_ui = client.get("/web-ui/asset.bin", headers=range_headers)
    resp_static = client.get("/web-static/asset.bin", headers=range_headers)

    assert resp_ui.status_code == resp_static.status_code == 206
    assert resp_ui.content == resp_static.content == b"0123"
    assert resp_ui.headers.get("Content-Range") == resp_static.headers.get("Content-Range")
    assert resp_ui.headers.get("ETag") and resp_static.headers.get("ETag")


def test_webui_serves_valid_files(webui_client: Tuple[TestClient, Dict[str, Path]]) -> None:
    client, _ = webui_client

    resp = client.get("/web-ui/index.html")
    assert resp.status_code == 200

    resp = client.get("/web-ui/nested/note.txt")
    assert resp.status_code == 200
    assert resp.text == "nested note"

    resp = client.get("/web-ui")
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "suspicious_path",
    [
        "../outside.txt",
        "%2e%2e/outside.txt",
        "%2e%2e%2Foutside.txt",
        "..%2foutside.txt",
        "..%5Coutside.txt",
        "..\\outside.txt",
        "nested/../../outside.txt",
    ],
)
def test_traversal_attempts_fail(
    webui_client: Tuple[TestClient, Dict[str, Path]],
    suspicious_path: str,
) -> None:
    client, _ = webui_client
    resp = client.get(f"/web-ui/{suspicious_path}")
    assert resp.status_code == 404


def test_symlink_outside_root_is_blocked(webui_client: Tuple[TestClient, Dict[str, Path]]) -> None:
    client, setup = webui_client
    symlink = setup.get("symlink")
    if symlink is None:
        pytest.skip("Symlinks not supported on this platform")

    resp = client.get(f"/web-ui/{symlink.name}")
    assert resp.status_code == 404
