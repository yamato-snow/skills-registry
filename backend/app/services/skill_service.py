"""Skill の永続化と検索.

zip_inspector が返した SkillPackage を DB とストレージに落とす層。
権限の概念はここに持ち込まない（design.md §6。認可は API 層の依存関数で扱う）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Skill, SkillVersion, Tag
from app.services import search
from app.services.zip_inspector import SkillPackage
from app.storage.base import StorageBackend

# 一覧・詳細で必ず使う関連。N+1 を避けるためまとめて読む。
# skill_md_body は deferred なのでここには乗らない（必要な場面だけ undefer する）
_EAGER = (selectinload(Skill.versions), selectinload(Skill.tags))
# 本文まで要るとき（検索のスコアリング・詳細ページ）用
_EAGER_WITH_BODY = (
    selectinload(Skill.versions).undefer(SkillVersion.skill_md_body),
    selectinload(Skill.tags),
)


@dataclass(frozen=True)
class SkillHit:
    """一覧 1 件分。Skill 本体と「なぜ当たったか」を組にして返す.

    ORM オブジェクトに検索結果の属性を後付けする手もあるが、それをすると
    「この属性はどこで生えたのか」がモデル定義を読んでも分からなくなる。
    """

    skill: Skill
    matched_fields: list[str]
    snippet: str | None


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
        # 検査のために既にメモリへ読んである全文。ここで捨てると、検索対象に
        # するにも詳細で見せるにも ZIP を開き直すことになる（ADR-007）
        skill_md_body=package.body,
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


def normalize_tags(tags: list[str] | None) -> list[str]:
    """タグ名を正規化する。取り込み時と同じ規則（trim + 小文字）で揃える."""
    normalized: list[str] = []
    for tag in tags or []:
        name = tag.strip().lower()
        if name and name not in normalized:
            normalized.append(name)
    return normalized


def _latest_version_subquery(*, include_body: bool):
    """各 Skill の最新版を 1 行に畳んだ subquery.

    検索対象の description / 本文も、並び順に使う created_at も、すべて
    「最新版のもの」でなければならないため、結合前に DISTINCT ON で畳む。

    列を明示して組み立てているのは、`select(SkillVersion)` にすると
    **deferred な skill_md_body が SELECT 句から落ちて** WHERE で参照できなく
    なるため。逆に、本文が要らない一覧では列に入れないことで、1MB × 件数を
    無条件に読む状態を避けている。
    """
    columns = [
        SkillVersion.skill_id,
        SkillVersion.description,
        SkillVersion.created_at,
    ]
    if include_body:
        columns.append(SkillVersion.skill_md_body)
    return (
        select(*columns)
        .distinct(SkillVersion.skill_id)
        .order_by(SkillVersion.skill_id, SkillVersion.version.desc())
        .subquery()
    )


async def list_skills(
    db: AsyncSession,
    *,
    q: str | None = None,
    tags: list[str] | None = None,
) -> list[SkillHit]:
    """一覧・検索（ADR-004 + ADR-006）.

    役割分担は「**SQL は絞り込み、Python は並べ替えと説明**」。

    - `q` は空白（半角・全角）で分割し、**全トークンが name / description /
      本文のいずれかに当たる** Skill だけを残す（AND）。トークンごとに
      OR を作り、それを AND で重ねる
    - `tags` も AND（絞り込みを重ねる操作として自然なほう）
    - `q` があるときだけ関連度順に並べ替える。無いときは従来どおり
      最新版の更新日時降順で、挙動は一切変わらない
    """
    tokens = search.tokenize(q)
    latest = _latest_version_subquery(include_body=bool(tokens))

    stmt = (
        select(Skill)
        .join(latest, Skill.id == latest.c.skill_id)
        .options(*(_EAGER_WITH_BODY if tokens else _EAGER))
    )

    for token in tokens:
        pattern = f"%{escape_like(token)}%"
        stmt = stmt.where(
            or_(
                Skill.name.ilike(pattern, escape="\\"),
                latest.c.description.ilike(pattern, escape="\\"),
                latest.c.skill_md_body.ilike(pattern, escape="\\"),
            )
        )

    for name in normalize_tags(tags):
        # any() は EXISTS を生成する。JOIN と違い結果行が重複しない。
        # タグごとに EXISTS を重ねることが、そのまま AND の意味になる
        stmt = stmt.where(Skill.tags.any(Tag.name == name))

    stmt = stmt.order_by(latest.c.created_at.desc())
    skills = list((await db.execute(stmt)).scalars().all())

    if not tokens:
        return [SkillHit(skill=skill, matched_fields=[], snippet=None) for skill in skills]

    scored: list[tuple[int, SkillHit]] = []
    for skill in skills:
        version = skill.latest_version
        assert version is not None  # 版のない Skill は登録経路上つくられない
        fields = {
            "name": skill.name,
            "description": version.description,
            "body": version.skill_md_body,
        }
        scored.append(
            (
                search.score(tokens, **fields),
                SkillHit(
                    skill=skill,
                    matched_fields=search.matched_fields(tokens, **fields),
                    snippet=search.extract_snippet(tokens, version.skill_md_body),
                ),
            )
        )

    # Python の sort は安定なので、SQL が付けた「更新日時降順」がそのまま
    # 同点時の順序として残る。同点の並びを別途書く必要がない
    scored.sort(key=lambda item: item[0], reverse=True)
    return [hit for _, hit in scored]


async def get_skill(
    db: AsyncSession, skill_id: uuid.UUID, *, with_body: bool = False
) -> Skill | None:
    """1 件取得。`with_body` のときだけ本文（deferred）まで読む.

    既定を False にしているのは、ダウンロード経路がこの関数を通るため。
    ZIP を返すだけの処理で最大 1MB × 版数のテキストを読む理由がない。
    """
    options = _EAGER_WITH_BODY if with_body else _EAGER
    stmt = select(Skill).where(Skill.id == skill_id).options(*options)
    return (await db.execute(stmt)).scalars().one_or_none()


def select_version(skill: Skill, version: int | None) -> SkillVersion | None:
    """版を選ぶ。version 省略時は最新版."""
    if version is None:
        return skill.latest_version
    return next((v for v in skill.versions if v.version == version), None)
