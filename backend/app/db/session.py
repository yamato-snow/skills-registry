"""DB エンジンとセッション."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    # 発行 SQL を見たいときは echo=True にする。既定で有効にすると本番ログが汚れる
    echo=False,
    # 接続が切れていた場合に取得時点で検知して張り直す。コンテナ再起動や
    # DB 側のアイドルタイムアウトで死んだ接続を掴むのを防ぐ
    pool_pre_ping=True,
)

# expire_on_commit=False: commit 後もインスタンスの属性を触れるようにする。
# async では属性アクセスが暗黙の再読み込み（= await できない I/O）を起こすため、
# これを切っておかないと commit 後のレスポンス組み立てで MissingGreenlet になる
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI の依存性注入用。リクエストごとに 1 セッション."""
    async with SessionLocal() as session:
        yield session
