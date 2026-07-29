"""FastAPI アプリケーションの組み立て."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import skills
from app.core.config import settings
from app.db import models  # noqa: F401  create_all にモデルを認識させるため import が必要
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # プロトタイプ判断として Alembic を入れず、起動時にテーブルを作る。
    # 「docker compose up 一発で動く」ことを優先した割り切りで、スキーマを
    # 変更したら volume を作り直す必要がある（design.md §3）。
    # データを消せなくなった時点が Alembic 導入の合図
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Skills Registry",
    description="Skills パッケージ（ZIP）の登録・検索・配布を行う社内向けレジストリ",
    version="0.1.0",
    lifespan=lifespan,
)

# ブラウザのアップロード画面から API を直接叩くため必要（ADR-005）。
# 許可オリジンは環境変数で注入する
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    # ブラウザ側で Content-Disposition を読めるようにする（ダウンロード名の取得）
    expose_headers=["Content-Disposition"],
)

app.include_router(skills.router)


@app.get("/health", tags=["meta"], summary="ヘルスチェック")
async def health() -> JSONResponse:
    """DB 接続まで確認する.

    プロセスの生存だけを返すヘルスチェックは、DB が落ちている状態でも
    「正常」と答えてしまう。ECS のヘルスチェックが依存先込みの可用性を
    見るように、SELECT 1 まで通す（design.md §4）。
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 原因を問わず不可用として扱う
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "detail": str(exc)},
        )
    return JSONResponse(content={"status": "ok"})
