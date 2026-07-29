"""LocalStorage の単体テスト（DB 不要）."""

from pathlib import Path

import pytest

from app.storage.local import LocalStorage, StorageKeyError


def test_保存して読み戻せる(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    storage.save("skills/abc/v1.zip", b"payload")

    assert storage.exists("skills/abc/v1.zip") is True
    with storage.open("skills/abc/v1.zip") as handle:
        assert handle.read() == b"payload"


def test_サブディレクトリが自動で作られる(tmp_path: Path):
    """キーは S3 互換の形で渡ってくるので、階層は実装側で作る（ADR-003）."""
    storage = LocalStorage(tmp_path)
    storage.save("a/b/c/d.zip", b"x")
    assert (tmp_path / "a" / "b" / "c" / "d.zip").is_file()


def test_存在しないキーはexistsがFalse(tmp_path: Path):
    assert LocalStorage(tmp_path).exists("nope.zip") is False


def test_削除は冪等(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    storage.save("x.zip", b"x")
    storage.delete("x.zip")
    storage.delete("x.zip")  # 2 回目もエラーにならない
    assert storage.exists("x.zip") is False


def test_保存先の外を指すキーを拒否する(tmp_path: Path):
    """キーは内部生成なので現状は起きないが、安全性を呼び出し元に依存させない."""
    storage = LocalStorage(tmp_path / "storage")
    with pytest.raises(StorageKeyError):
        storage.save("../escaped.zip", b"x")


def test_絶対パスのキーも拒否する(tmp_path: Path):
    storage = LocalStorage(tmp_path / "storage")
    with pytest.raises(StorageKeyError):
        storage.save("/etc/passwd", b"x")
