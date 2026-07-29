"""Skill の永続化と検索.

zip_inspector が返した SkillPackage を DB とストレージに落とす層。
権限の概念はここに持ち込まない（design.md §6。認可は API 層の依存関数で扱う）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.db.models import Skill, SkillVersion, Tag
from app.services.zip_inspector import SkillPackage
from app.storage.base import StorageBackend

# 一覧・詳細で必ず使う関連。N+1 を避けるためまとめて読む
_EAGER = (selectinload(Skill.versions), selectinload(Skill.tags))


def build_storage_key(skill_id: uuid.UUID, version: int) -> str:
    """S3 互換のキー体系（ADR-003）。ローカル実装ではそのままサブディレクトリになる."""
    return f"skills/{skill_id}/v{version}.zip"


def escape_like(value: str) -> str:
    """ILIKE のワイルドカードを無効化する.

    SQL インジェクションはバインドパラメータで防げるが、`%` や `_` が
    ワイルドカードとして解釈される問題はそれとは別。`my_skill` を検索した
    利用者は `_` を 1 文字ワイルドカードのつもりで書いていない（ADR-004）。
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _get_or_create_tags(db: AsyncSession, names: list[str]) -> list[Tag]:
    if not names:
        return []
    existing = (await db.execute(select(Tag).where(Tag.name.in_(names)))).scalars().all()
    by_name = {tag.name: tag for tag in existing}
    for name in names:
        if name not in by_name:
            tag = Tag(name=name)
            db.add(tag)
            by_name[name] = tag
    return [by_name[name] for name in names]


async def _get_skill_by_name(db: AsyncSession, name: str) -> Skill | None:
    stmt = select(Skill).where(Skill.name == name).options(*_EAGER)
    return (await db.execute(stmt)).scalars().one_or_none()


async def register_skill(
    db: AsyncSession,
    storage: StorageBackend,
    package: SkillPackage,
    raw: bytes,
) -> tuple[Skill, SkillVersion]:
    """検証済みパッケージを登録する。同名が既にあれば新しい版として追加する.

    保存順序は **ストレージ → DB コミット** の順で固定している（design.md §4）。
    逆順にすると、ストレージ書き込みに失敗したときに「DB にはあるが
    ダウンロードできないレコード」が残る。この順なら残るのは孤児ファイルだけで、
    利用者からは見えず、後から掃除できる。
    """
    skill = await _get_skill_by_name(db, package.name)
    if skill is None:
        db.add(Skill(name=package.name))
        try:
            # id を採番するために flush する（ストレージキーの組み立てに必要）
            await db.flush()
        except IntegrityError:
            # 同名の Skill が別リクエストで同時に作られた。name の UNIQUE 制約が
            # 検出してくれるので、ここでは既存レコードを読み直して版追加へ回る
            await db.rollback()
        # 取り直すのは、関連（versions / tags）をロード済みの状態にするため。
        # flush 直後の新規インスタンスは関連が未ロードで、以降で触ると
        # 暗黙の lazy load（= await できない I/O）が走り MissingGreenlet になる
        skill = await _get_skill_by_name(db, package.name)
        if skill is None:  # pragma: no cover - 直前に作った行が無いのは異常系
            raise RuntimeError(f"Skill の作成に失敗しました: {package.name}")

    next_version = max((v.version for v in skill.versions), default=0) + 1
    storage_key = build_storage_key(skill.id, next_version)

    # DB へ書く前にファイルを置く
    storage.save(storage_key, raw)

    version = SkillVersion(
        skill_id=skill.id,
        version=next_version,
        description=package.description,
        file_tree=[entry.to_dict() for entry in package.file_tree],
        storage_key=storage_key,
        size_bytes=len(raw),
    )
    db.add(version)

    # タグは Skill 単位。再アップロード時は最新 frontmatter の内容で張り替える
    skill.tags = await _get_or_create_tags(db, package.tags)

    await db.commit()

    refreshed = await _get_skill_by_name(db, package.name)
    assert refreshed is not None  # commit 直後なので必ず取れる
    return refreshed, version


async def list_skills(
    db: AsyncSession,
    *,
    q: str | None = None,
    tag: str | None = None,
) -> list[Skill]:
    """一覧・検索（ADR-004）.

    各 Skill の「最新版」を DISTINCT ON で 1 行に畳んでから結合する。
    検索対象の description と、並び順に使う created_at は、どちらも
    最新版のものでなければならないため。
    """
    latest_subq = (
        select(SkillVersion)
        .distinct(SkillVersion.skill_id)
        .order_by(SkillVersion.skill_id, SkillVersion.version.desc())
        .subquery()
    )
    latest = aliased(SkillVersion, latest_subq)

    stmt = select(Skill).join(latest, Skill.id == latest.skill_id).options(*_EAGER)

    if q:
        pattern = f"%{escape_like(q)}%"
        stmt = stmt.where(
            or_(
                Skill.name.ilike(pattern, escape="\\"),
                latest.description.ilike(pattern, escape="\\"),
            )
        )
    if tag:
        # any() は EXISTS を生成する。JOIN と違い結果行が重複しない
        stmt = stmt.where(Skill.tags.any(Tag.name == tag.strip().lower()))

    stmt = stmt.order_by(latest.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def get_skill(db: AsyncSession, skill_id: uuid.UUID) -> Skill | None:
    stmt = select(Skill).where(Skill.id == skill_id).options(*_EAGER)
    return (await db.execute(stmt)).scalars().one_or_none()


def select_version(skill: Skill, version: int | None) -> SkillVersion | None:
    """版を選ぶ。version 省略時は最新版."""
    if version is None:
        return skill.latest_version
    return next((v for v in skill.versions if v.version == version), None)
