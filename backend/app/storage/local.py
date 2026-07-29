"""ローカルファイルシステムへの保存（ADR-003 の LocalStorage）.

キーは S3 互換の形（skills/{skill_id}/v{version}.zip）で受け取り、そのまま
サブディレクトリとして解釈する。S3 へ移行する際に `aws s3 sync` 相当で
データを持っていけるようにするため。
"""

from pathlib import Path
from typing import BinaryIO


class StorageKeyError(ValueError):
    """保存先ディレクトリの外を指すキーを渡された."""


class LocalStorage:
    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """キーを実パスへ解決し、base_dir の外に出ていないことを確認する.

        キーはアプリが内部生成する（UUID + 版番号）ので、現状の呼び出し経路では
        危険なキーは発生しない。それでも検証するのは、安全性を「呼び出し元が
        正しいこと」に依存させないため（ADR-002 と同じ考え方）。
        """
        path = (self._base / key).resolve()
        if not path.is_relative_to(self._base):
            raise StorageKeyError(f"保存先の外を指すキーです: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def open(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)
