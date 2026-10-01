import io
from types import SimpleNamespace

import pytest
from storage3.exceptions import StorageApiError

from src.config import Settings
from src.infrastructure.storage import (
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    create_file_storage,
    join_key,
    normalize_key,
    safe_key,
    safe_key_segment,
)
from src.infrastructure.storage.supabase_store import SupabaseFileStorage


class FakeBucket:
    """In-memory stand-in for storage3's bucket API (only what the adapter calls)."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict]] = {}

    def upload(self, path, file, file_options):
        if path in self.objects and file_options.get("upsert") != "true":
            raise StorageApiError("The resource already exists", "Duplicate", 409)
        self.objects[path] = (file, dict(file_options))

    def download(self, path):
        if path not in self.objects:
            raise StorageApiError("Object not found", "not_found", 404)
        return self.objects[path][0]

    def exists(self, path):
        return path in self.objects

    def remove(self, paths):
        removed = [p for p in paths if self.objects.pop(p, None) is not None]
        return [{"name": p} for p in removed]

    def move(self, src, dst):
        self.objects[dst] = self.objects.pop(src)

    def copy(self, src, dst):
        self.objects[dst] = self.objects[src]

    def list(self, path, options):
        prefix = f"{path}/" if path else ""
        files, folders = [], set()
        for key, (body, opts) in sorted(self.objects.items()):
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix) :]
            if "/" in rest:
                folders.add(rest.split("/", 1)[0])
            else:
                files.append(
                    {
                        "name": rest,
                        "id": key,
                        "updated_at": "2026-09-29T10:00:00Z",
                        "metadata": {"size": len(body), "mimetype": opts["content-type"]},
                    }
                )
        rows = [{"name": f, "id": None, "metadata": None} for f in sorted(folders)] + files
        return rows[options["offset"] : options["offset"] + options["limit"]]

    def create_signed_url(self, path, expires_in, options):
        return {"signedURL": f"https://x/{path}?exp={expires_in}", "signedUrl": None}

    def create_signed_urls(self, paths, expires_in):
        return [{"path": p, "signedURL": f"https://x/{p}", "error": None} for p in paths]


@pytest.fixture
def bucket() -> FakeBucket:
    return FakeBucket()


@pytest.fixture
def storage(bucket: FakeBucket) -> SupabaseFileStorage:
    client = SimpleNamespace(storage=SimpleNamespace(from_=lambda name: bucket))
    return SupabaseFileStorage(client, "documents")


# -- key helpers ------------------------------------------------------------
def test_normalize_key_cleans_windows_and_slashes():
    assert normalize_key("\\manuals//vf8\\guide.pdf/") == "manuals/vf8/guide.pdf"


@pytest.mark.parametrize("key", ["", "/", "a/../b", "./a"])
def test_normalize_key_rejects_invalid(key):
    with pytest.raises(ValueError):
        normalize_key(key)


def test_safe_key_transliterates_vietnamese():
    assert safe_key_segment("Sổ tay bảo dưỡng Đời VF8.pdf") == "So-tay-bao-duong-Doi-VF8.pdf"
    assert safe_key("Tài liệu/Hướng dẫn (v2).pdf") == "Tai-lieu/Huong-dan-v2.pdf"


def test_join_key():
    assert join_key("", "a.pdf") == "a.pdf"
    assert join_key("manuals/", "/vf8/a.pdf") == "manuals/vf8/a.pdf"


# -- adapter ----------------------------------------------------------------
def test_upload_guesses_content_type_and_roundtrips(storage, bucket):
    obj = storage.upload("/manuals/a.pdf", b"%PDF", metadata={"original_name": "á.pdf"})
    assert obj.key == "manuals/a.pdf"
    assert obj.size == 4
    assert bucket.objects["manuals/a.pdf"][1]["content-type"] == "application/pdf"
    assert bucket.objects["manuals/a.pdf"][1]["metadata"] == {"original_name": "á.pdf"}
    assert storage.download("manuals/a.pdf") == b"%PDF"


def test_upload_accepts_file_like(storage):
    storage.upload("a.txt", io.BytesIO(b"hello"))
    assert storage.download("a.txt") == b"hello"


def test_upload_conflict_and_overwrite(storage):
    storage.upload("a.pdf", b"1")
    with pytest.raises(StorageConflictError):
        storage.upload("a.pdf", b"2")
    storage.upload("a.pdf", b"2", overwrite=True)
    assert storage.download("a.pdf") == b"2"


def test_download_missing_raises_not_found(storage):
    with pytest.raises(StorageNotFoundError):
        storage.download("missing.pdf")


def test_not_found_is_a_storage_error(storage):
    with pytest.raises(StorageError):
        storage.download("missing.pdf")


def test_upload_file_uses_safe_name(storage, tmp_path):
    local = tmp_path / "Sổ tay.pdf"
    local.write_bytes(b"%PDF")
    obj = storage.upload_file(local)
    assert obj.key == "So-tay.pdf"
    assert obj.content_type == "application/pdf"


def test_download_to_directory(storage, tmp_path):
    storage.upload("manuals/a.pdf", b"%PDF")
    target = storage.download_to("manuals/a.pdf", tmp_path)
    assert target == tmp_path / "a.pdf"
    assert target.read_bytes() == b"%PDF"


def test_list_returns_files_and_folders(storage):
    storage.upload("manuals/a.pdf", b"1")
    storage.upload("manuals/vf8/b.pdf", b"22")
    items = storage.list("manuals")
    assert [(o.key, o.is_folder) for o in items] == [("manuals/vf8", True), ("manuals/a.pdf", False)]
    assert items[1].size == 1
    assert items[1].content_type == "application/pdf"
    assert items[1].updated_at is not None


def test_iter_objects_recursive_and_paginated(storage):
    for i in range(5):
        storage.upload(f"root/{i}.txt", b"x")
    storage.upload("root/sub/deep.txt", b"x")
    flat = sorted(o.key for o in storage.iter_objects("root", page_size=2))
    assert flat == [f"root/{i}.txt" for i in range(5)]
    deep = sorted(o.key for o in storage.iter_objects("root", recursive=True, page_size=2))
    assert deep == [f"root/{i}.txt" for i in range(5)] + ["root/sub/deep.txt"]


def test_delete_move_copy_exists(storage):
    storage.upload("a.txt", b"x")
    storage.copy("a.txt", "b.txt")
    storage.move("b.txt", "c.txt")
    assert storage.exists("a.txt") and storage.exists("c.txt")
    assert not storage.exists("b.txt")
    assert storage.delete(["a.txt", "missing.txt"]) == ["a.txt"]
    assert storage.delete_prefix("") == ["c.txt"]


def test_signed_urls(storage):
    assert storage.signed_url("a.pdf", 60) == "https://x/a.pdf?exp=60"
    assert storage.signed_urls(["a.pdf", "b.pdf"], 60) == {"a.pdf": "https://x/a.pdf", "b.pdf": "https://x/b.pdf"}


# -- factory ----------------------------------------------------------------
def test_factory_requires_credentials():
    with pytest.raises(StorageError):
        create_file_storage(Settings(_env_file=None, supabase_url="", supabase_key=""))


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError):
        create_file_storage(Settings(_env_file=None), backend="s3")
