"""依存性注入.

ストレージ実装をここで 1 箇所に閉じ込めている。S3 へ移行するときに触るのは
このファイルの 1 行だけ、というのが ADR-003 で狙った状態。

認証・認可を実装する場合もここに require_role() を足し、各ルートの
dependencies に宣言する（design.md §6）。
"""

from functools import lru_cache

from app.core.config import settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage


@lru_cache
def _storage_instance() -> StorageBackend:
    # ここを S3Storage(...) に差し替えれば本番構成になる
    return LocalStorage(settings.storage_dir)


def get_storage() -> StorageBackend:
    return _storage_instance()
