"""テストの共通フィクスチャ.

API テストは **SQLite で代用せず、実 PostgreSQL に対して回す**。JSONB・
DISTINCT ON・ILIKE の挙動は PostgreSQL 固有で、SQLite で通しても本番の
保証にならない（design.md の技術選定どおり）。

DB が起動していない環境では API テストだけがスキップされる（zip_inspector の
単体テストは DB に依存しないので常に走る）。CI では services で PostgreSQL を
立てるため、スキップは発生しない。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.deps import get_storage
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.main import app
from app.storage.local import LocalStorage


async def _ensure_test_database() -> None:
    """テスト用 DB（<開発用>_test）が無ければ作る.

    CREATE DATABASE はトランザクション内で実行できないので AUTOCOMMIT で繋ぐ。
    接続先は同じサーバの管理用 DB（postgres）。
    """
    url = make_url(settings.database_url)
    target = url.database
    admin_engine = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target}
            )
            if not exists:
                # DB 名は内部生成（設定値 + _test）なので、識別子として直接埋め込む
                await conn.execute(text(f'CREATE DATABASE "{target}"'))
    finally:
        await admin_engine.dispose()


def database_reachable() -> bool:
    """DB へ接続できるか（test_api_skills のスキップ判定に使う）.

    フィクスチャの外＝イベントループが立つ前に呼ばれるので、
    使い捨てのループで確認する。ついでにテスト用 DB を用意する。
    """

    async def check() -> bool:
        try:
            await _ensure_test_database()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    try:
        return asyncio.run(check())
    finally:
        # 使い捨てループで作った接続をプールに残さない
        asyncio.run(engine.dispose())


@pytest.fixture(scope="session")
async def schema() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture
async def clean_tables(schema: None) -> AsyncGenerator[None, None]:
    """各テストの前に全テーブルを空にする.

    テスト間の独立性をトランザクションのロールバックではなく TRUNCATE で
    確保している。アプリ側が自分で commit する（register_skill）ため、
    外側のトランザクションで包む方式が使えないため。
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE skill_tags, skill_versions, tags, skills RESTART IDENTITY CASCADE")
        )
    yield


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
async def client(clean_tables: None, storage: LocalStorage) -> AsyncGenerator[AsyncClient, None]:
    # ストレージだけテスト用の一時ディレクトリへ差し替える。
    # DI を 1 箇所へ集約した効果がここに出る（ADR-003）
    app.dependency_overrides[get_storage] = lambda: storage
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
