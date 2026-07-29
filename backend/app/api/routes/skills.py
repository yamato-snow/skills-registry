"""Skills のエンドポイント."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_storage
from app.core.config import settings
from app.db.session import get_db
from app.schemas.skill import SkillDetailOut, SkillSummaryOut, UploadResultOut
from app.services import skill_service
from app.services.zip_inspector import (
    ArchiveTooLargeError,
    InvalidArchiveError,
    InvalidPackageError,
    inspect_skill_zip,
)
from app.storage.base import StorageBackend

router = APIRouter(prefix="/skills", tags=["skills"])

# 依存は Annotated で型に埋め込む。引数の既定値に Depends(...) を書く旧来の書き方は
# 「引数のデフォルト値で関数呼び出しをしている」ため lint（flake8-bugbear B008）に
# 引っかかる。Annotated なら型注釈側に寄るので、その指摘を抑制せずに済む
DbSession = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[StorageBackend, Depends(get_storage)]

# 検証エラーを HTTP ステータスへ写像する。
# 400 = 壊れた入力 / 413 = 大きすぎる入力 / 422 = 形式は合っているが要件未達
_ERROR_STATUS = {
    InvalidArchiveError: status.HTTP_400_BAD_REQUEST,
    ArchiveTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    InvalidPackageError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    """アップロードを上限付きで読み込む.

    file.read() を無制限に呼ぶと、上限超過の巨大ボディをメモリに載せてから
    弾くことになる。limit + 1 バイトで打ち切れば、超過は検出できて
    メモリは上限までに収まる。
    """
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining > 0:
        chunk = await file.read(min(remaining, 1024 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


@router.post(
    "",
    response_model=UploadResultOut,
    status_code=status.HTTP_201_CREATED,
    summary="Skills パッケージ（ZIP）を登録する",
)
async def upload_skill(
    db: DbSession,
    storage: Storage,
    file: Annotated[UploadFile, File(description="SKILL.md を含む ZIP")],
) -> UploadResultOut:
    raw = await _read_upload(file, settings.max_total_size)
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="ファイルが空です。")
    if len(raw) > settings.max_total_size:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"ファイルサイズが上限（{settings.max_total_size // (1024 * 1024)}MB）を"
                "超えています。"
            ),
        )

    try:
        package = inspect_skill_zip(
            raw,
            max_total_size=settings.max_total_size,
            max_files=settings.max_files,
            max_skill_md_size=settings.max_skill_md_size,
        )
    except tuple(_ERROR_STATUS) as exc:
        raise HTTPException(_ERROR_STATUS[type(exc)], detail=str(exc)) from exc

    skill, version = await skill_service.register_skill(db, storage, package, raw)
    return UploadResultOut.from_model(skill, version)


@router.get("", response_model=list[SkillSummaryOut], summary="一覧・検索")
async def list_skills(
    db: DbSession,
    q: Annotated[str | None, Query(description="name / description への部分一致")] = None,
    tag: Annotated[str | None, Query(description="タグの完全一致")] = None,
) -> list[SkillSummaryOut]:
    skills = await skill_service.list_skills(db, q=q, tag=tag)
    return [SkillSummaryOut.from_model(skill) for skill in skills]


@router.get("/{skill_id}", response_model=SkillDetailOut, summary="詳細")
async def get_skill(skill_id: uuid.UUID, db: DbSession) -> SkillDetailOut:
    skill = await skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill が見つかりません。")
    return SkillDetailOut.from_model(skill)


@router.get("/{skill_id}/download", summary="ZIP 原本のダウンロード")
async def download_skill(
    skill_id: uuid.UUID,
    db: DbSession,
    storage: Storage,
    version: Annotated[int | None, Query(description="省略時は最新版")] = None,
) -> StreamingResponse:
    skill = await skill_service.get_skill(db, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Skill が見つかりません。")

    target = skill_service.select_version(skill, version)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="指定された版が見つかりません。")
    if not storage.exists(target.storage_key):  # pragma: no cover - 通常は起きない
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ファイル本体が見つかりません。")

    filename = f"{skill.name}-v{target.version}.zip"

    def iterfile() -> Iterator[bytes]:
        # ストリームで流す。50MB をメモリへ全載せしない（ADR-003 で open() が
        # bytes ではなくストリームを返す理由）
        with storage.open(target.storage_key) as handle:
            while chunk := handle.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="application/zip",
        headers={
            # 日本語の Skill 名に対応するため RFC 5987 形式を併記する。
            # ASCII 版は互換性のためのフォールバック
            "Content-Disposition": (
                f'attachment; filename="skill-v{target.version}.zip"; '
                f"filename*=UTF-8''{quote(filename)}"
            ),
            "Content-Length": str(target.size_bytes),
        },
    )
