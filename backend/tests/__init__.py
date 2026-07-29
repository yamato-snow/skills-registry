"""テスト実行時の環境調整.

**このファイルは conftest.py より先に実行される**（tests がパッケージなので、
pytest が tests.conftest を import する前に tests/__init__.py が走る）。
アプリの DB エンジンは app.db.session の import 時に settings.database_url から
作られるため、「テスト用 DB へ向ける」書き換えはこのタイミングでしかできない。

開発用の DB をそのままテストに使うと、テスト前の TRUNCATE が手元の
アップロード済みデータを消してしまう（実際に一度消した。learnings.md 参照）。
DB 名の末尾に _test を付けて隔離する。DB が無ければ conftest が作る。
"""

import os

# compose の db はホスト側 55432 に出している（5432 は他プロジェクトと衝突しやすい）
_DEFAULT_URL = "postgresql+asyncpg://postgres:postgres@localhost:55432/skills_registry"

_url = os.environ.get("DATABASE_URL", _DEFAULT_URL)
if not _url.endswith("_test"):
    _url = f"{_url}_test"
os.environ["DATABASE_URL"] = _url
