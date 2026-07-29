"""ORM モデル（design.md §3 の ER 図に対応）."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Skill とタグの多対多。属性を持たない純粋な関連なので Core の Table で表現する
skill_tags = Table(
    "skill_tags",
    Base.metadata,
    Column(
        "skill_id",
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Skill(Base):
    """Skills パッケージ（名前で識別される論理的な 1 つの Skill）."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # SKILL.md の frontmatter の name。**これが同一性の基準**で、同名の再アップロードは
    # 新しい Skill ではなく新しい版になる。UNIQUE 制約で並行登録も DB 側で弾く
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    versions: Mapped[list["SkillVersion"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
        order_by="SkillVersion.version",
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=skill_tags, back_populates="skills")

    @property
    def latest_version(self) -> "SkillVersion | None":
        # versions は version 昇順で読み込まれるので末尾が最新
        return self.versions[-1] if self.versions else None


class SkillVersion(Base):
    """アップロード 1 回分。ZIP 原本とそのメタデータ."""

    __tablename__ = "skill_versions"
    __table_args__ = (
        # 同一 Skill 内で版番号が重複しないことを DB で保証する。
        # 版番号はアプリ側で採番するため、並行アップロード時の衝突はここで検出する
        UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_id_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    # Skill 内の連番（1 始まり）。グローバルな連番ではない
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # 説明文は版ごとに変わりうるので Skill ではなく版に持つ
    description: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    # frontmatter を除いた SKILL.md 本文（ADR-007）。name / description は
    # 構造化して別に持っているので、ここに再掲すると検索のヒット判定が濁る。
    # deferred にしているのは、一覧が最大 1MB × 件数を無条件に引くのを避けるため。
    # 必要な箇所（検索時のスコアリング・詳細ページ）だけ undefer して読む
    skill_md_body: Mapped[str] = mapped_column(Text, nullable=False, default="", deferred=True)
    # ZIP の中身一覧 [{"path": ..., "size": ...}]。詳細画面のために ZIP を開き直さない（ADR-002）
    file_tree: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # S3 互換のキー体系。ローカル実装ではそのままサブディレクトリになる（ADR-003）
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    skill: Mapped[Skill] = relationship(back_populates="versions")


class Tag(Base):
    """frontmatter の tags から取り込むタグ（Skill 単位・版単位ではない）."""

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    skills: Mapped[list[Skill]] = relationship(secondary=skill_tags, back_populates="tags")
