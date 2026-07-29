"""API のレスポンススキーマ（Pydantic v2）.

ORM モデルをそのまま返さないのは、DB の都合（storage_key など内部情報）を
API の契約に漏らさないため。storage_key が外に出ると、将来 S3 へ移した際に
互換性の議論が発生してしまう。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import Skill, SkillVersion


class FileEntryOut(BaseModel):
    path: str
    size: int


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    size_bytes: int
    created_at: datetime


class SkillSummaryOut(BaseModel):
    """一覧に出す 1 件分（最新版のメタデータ）."""

    id: uuid.UUID
    name: str
    description: str
    tags: list[str]
    latest_version: int
    updated_at: datetime

    @classmethod
    def from_model(cls, skill: Skill) -> "SkillSummaryOut":
        latest = skill.latest_version
        assert latest is not None  # 版のない Skill は登録経路上つくられない
        return cls(
            id=skill.id,
            name=skill.name,
            description=latest.description,
            tags=sorted(tag.name for tag in skill.tags),
            latest_version=latest.version,
            updated_at=latest.created_at,
        )


class SkillDetailOut(SkillSummaryOut):
    """詳細。一覧の内容 + 最新版のファイルツリー + 全版の履歴."""

    file_tree: list[FileEntryOut]
    versions: list[VersionOut]

    @classmethod
    def from_model(cls, skill: Skill) -> "SkillDetailOut":
        summary = SkillSummaryOut.from_model(skill)
        latest = skill.latest_version
        assert latest is not None
        return cls(
            **summary.model_dump(),
            file_tree=[FileEntryOut(**entry) for entry in latest.file_tree],
            # 新しい版を上に出す
            versions=[VersionOut.model_validate(v) for v in reversed(skill.versions)],
        )


class UploadResultOut(BaseModel):
    """アップロード成功時。作成された版を明示する."""

    id: uuid.UUID
    name: str
    version: int
    created: bool  # True: 新規 Skill / False: 既存 Skill への版追加

    @classmethod
    def from_model(cls, skill: Skill, version: SkillVersion) -> "UploadResultOut":
        return cls(
            id=skill.id,
            name=skill.name,
            version=version.version,
            created=version.version == 1,
        )


class ErrorOut(BaseModel):
    """エラーレスポンス。メッセージはそのまま画面に出せる日本語."""

    detail: str
