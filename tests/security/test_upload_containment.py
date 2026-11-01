"""P0-2 acceptance against the actual upload store and authenticated API."""

import hashlib
import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from moro.dashboard import uploads
from moro.dashboard.mission_control import app

GOOD = b'{"prompt":"hi","completion":"hello"}\n'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MORO_API_TOKEN", "upload-acceptance-" + "a" * 32)
    for module in ["mission_control", "utils", "security", "api.datasets"]:
        monkeypatch.setattr(f"moro.dashboard.{module}.get_project_root", lambda: tmp_path)
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer upload-acceptance-" + "a" * 32},
    ) as c:
        yield c


def store(root, content=GOOD, filename="source.jsonl", **kwargs):
    return uploads.store_upload(root, UploadFile(io.BytesIO(content), filename=filename), **kwargs)


def assert_empty(root):
    assert not list((root / "data/raw").iterdir())


@pytest.mark.parametrize("component", ["data", "raw"])
def test_directory_symlink_is_rejected(tmp_path, component):
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = tmp_path if component == "data" else tmp_path / "data"
    parent.mkdir(exist_ok=True)
    (parent / component).symlink_to(outside, target_is_directory=True)
    with pytest.raises(HTTPException) as error:
        store(tmp_path)
    assert error.value.status_code == 400
    assert not list(outside.iterdir())


def test_parent_swap_cannot_redirect_child_open(tmp_path, monkeypatch):
    (tmp_path / "data/raw").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    real_open = os.open
    swapped = False

    def swap(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "raw" and not swapped:
            swapped = True
            (tmp_path / "data").rename(tmp_path / "original-data")
            (tmp_path / "data").symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(uploads.os, "open", swap)
    store(tmp_path)
    assert not list(outside.iterdir())
    assert len(list((tmp_path / "original-data/raw").glob("*.jsonl"))) == 1


@pytest.mark.parametrize("kind", ["file", "symlink", "metadata", "staging"])
def test_exact_target_collisions_never_overwrite(tmp_path, monkeypatch, kind):
    raw = uploads.raw_directory(tmp_path)
    monkeypatch.setattr(uploads, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    name = "a" * 32 + ".jsonl"
    target = raw / (
        ".upload-" + "a" * 32
        if kind == "staging"
        else f".{name}.metadata"
        if kind == "metadata"
        else name
    )
    victim = tmp_path / "victim"
    victim.write_bytes(b"ORIGINAL")
    if kind == "symlink":
        target.symlink_to(victim)
    else:
        target.write_bytes(b"ORIGINAL")
    with pytest.raises(HTTPException) as error:
        store(tmp_path)
    assert error.value.status_code == 409
    assert target.read_bytes() == b"ORIGINAL"
    assert victim.read_bytes() == b"ORIGINAL"
    assert list(raw.iterdir()) == [target]


def test_collision_planted_at_publication_is_atomic(tmp_path, monkeypatch):
    real_link = os.link

    def collide(src, dst, **kwargs):
        fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=kwargs["dst_dir_fd"])
        os.write(fd, b"WINNER")
        os.close(fd)
        return real_link(src, dst, **kwargs)

    monkeypatch.setattr(uploads.os, "link", collide)
    with pytest.raises(HTTPException) as error:
        store(tmp_path)
    assert error.value.status_code == 409
    files = list((tmp_path / "data/raw").iterdir())
    assert len(files) == 1 and files[0].read_bytes() == b"WINNER"


@pytest.mark.parametrize(
    "content,filename",
    [
        (b"\xff", "data.txt"),
        (b"valid\x00binary", "data.txt"),
        (b"", "data.jsonl"),
        (b"42\n", "data.jsonl"),
        (b"[]", "data.json"),
        (b"[{} , 5]", "data.json"),
        (b'{"value":NaN}', "data.json"),
        (b"just prose\n", "data.csv"),
        (b"a,a\n1,2\n", "data.csv"),
        (b"a,b\n1\n", "data.csv"),
        (b'a,b\n"unclosed,2\n', "data.csv"),
        (GOOD * 30000 + b"not json\n", "data.jsonl"),
        (GOOD * 30000 + b"\xff", "data.jsonl"),
        (b"[" * 2000 + b"{}" + b"]" * 2000, "data.json"),
    ],
)
def test_invalid_entire_content_leaves_no_objects(tmp_path, content, filename):
    with pytest.raises(HTTPException) as error:
        store(tmp_path, content, filename)
    assert error.value.status_code == 400
    assert_empty(tmp_path)


def test_exact_size_boundary_and_private_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", len(GOOD))
    path = store(tmp_path, display_name="../../private\x00name\n.jsonl")
    metadata = uploads.read_upload_metadata(path)
    assert metadata["sha256"] == hashlib.sha256(GOOD).hexdigest()
    assert metadata["row_count"] == 1
    assert metadata["size_bytes"] == len(GOOD)
    assert "/" not in metadata["display_name"] and "\x00" not in metadata["display_name"]
    for file in path.parent.iterdir():
        assert file.stat().st_mode & 0o777 == 0o600
    with pytest.raises(HTTPException) as error:
        store(tmp_path, GOOD + b" ")
    assert error.value.status_code == 413
    assert len(list(path.parent.iterdir())) == 2


def test_read_failure_cleans_staging(tmp_path):
    class BrokenStream(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("injected read failure")
            return super().read(10)

    with pytest.raises(OSError, match="injected"):
        uploads.store_upload(tmp_path, UploadFile(BrokenStream(GOOD), filename="a.jsonl"))
    assert_empty(tmp_path)


def test_metadata_failure_rolls_back_payload(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("injected metadata write failure")

    monkeypatch.setattr(uploads.json, "dump", fail)
    with pytest.raises(OSError, match="injected"):
        store(tmp_path)
    assert_empty(tmp_path)


def test_metadata_symlink_is_not_read(tmp_path):
    path = store(tmp_path)
    metadata = path.parent / f".{path.name}.metadata"
    metadata.unlink()
    metadata.symlink_to(tmp_path / "nonexistent")
    with pytest.raises(HTTPException) as error:
        uploads.read_upload_metadata(path)
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "filename,content,expected",
    [
        ("records.json", b'[{"x":1},{"x":2}]', [{"x": 1}]),
        ("records.jsonl", b'\n\n{"x":1}\n{"x":2}\n', [{"x": 1}]),
        ("records.csv", b'x,y\n"first\nline",a\nsecond,b\n', [{"x": "first\nline", "y": "a"}]),
    ],
)
def test_upload_list_preview_delete_preserves_metadata(
    client, tmp_path, filename, content, expected
):
    r = client.post(
        "/api/datasets/upload",
        files={"file": (filename, content)},
        data={"display_name": "../../Friendly upload"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sha256"] == hashlib.sha256(content).hexdigest()
    assert data["name"] == ".._.._Friendly upload"
    path = Path(data["path"])
    assert path.parent == tmp_path / "data/raw"
    listing = client.get("/api/datasets/").json()
    assert len(listing) == 1 and listing[0]["name"] == data["name"]
    assert listing[0]["row_count"] == 2 and listing[0]["upload_sha256"] == data["sha256"]
    preview = client.get(f"/api/datasets/{data['dataset_id']}/preview", params={"limit": 1})
    assert preview.status_code == 200
    assert preview.json()["row_count"] == 2
    assert preview.json()["sample_rows"] == expected
    assert client.delete(f"/api/datasets/{data['dataset_id']}").status_code == 200
    assert_empty(tmp_path)


def test_dangling_symlink_does_not_break_listing(client, tmp_path):
    raw = uploads.raw_directory(tmp_path)
    (raw / "dangling.jsonl").symlink_to(tmp_path / "missing")
    assert client.get("/api/datasets/").status_code == 200


def test_batch_reports_each_result(client, tmp_path):
    r = client.post(
        "/api/datasets/upload/multiple",
        files=[
            ("files", ("valid.jsonl", GOOD)),
            ("files", ("bad.jsonl", b"bad")),
            ("files", ("second.jsonl", GOOD)),
        ],
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_uploaded"] == 2
    assert [item["status"] for item in r.json()["results"]] == ["uploaded", "rejected", "uploaded"]
    assert len(list((tmp_path / "data/raw").glob("*.jsonl"))) == 2


def test_metadata_is_not_an_addressable_dataset(client, tmp_path):
    path = store(tmp_path)
    name = f".{path.name}.metadata"
    assert client.get(f"/api/datasets/{name}/preview").status_code == 404
    assert client.delete(f"/api/datasets/{name}").status_code == 404
    assert (path.parent / name).exists()


def test_batch_compile_failure_reports_saved_id(client, tmp_path, monkeypatch):
    def fail(path):
        raise ValueError("injected compiler failure")

    monkeypatch.setattr("moro.dashboard.api.datasets.compile_dataset_sync", fail)
    r = client.post(
        "/api/datasets/upload/multiple",
        files=[("files", ("valid.jsonl", GOOD))],
        data={"auto_compile": "true"},
    )
    assert r.status_code == 200
    assert r.json()["total_uploaded"] == 1
    item = r.json()["results"][0]
    assert item["status"] == "saved_compile_failed" and item["status_code"] == 422
    assert client.get(f"/api/datasets/{item['detail']['dataset_id']}/preview").status_code == 200
