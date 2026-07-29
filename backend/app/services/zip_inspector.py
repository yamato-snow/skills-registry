"""ZIP の安全性検証と Skills メタデータの抽出.

このモジュールは **FastAPI にも SQLAlchemy にも依存しない**。入力は bytes、
出力はデータクラスで、HTTP もリクエストコンテキストも DB も知らない。

そうしている理由は 2 つある（design.md §5）。

1. ここがシステムのセキュリティ境界そのものなので、HTTP の文脈なしに
   単体でテストしきれることに価値がある（カバレッジ目標 90%+）
2. ADR-001 の移行基準に抵触して非同期ワーカーへ移す日が来ても、
   呼び出し元を差し替えるだけでロジックはそのまま動く

**設計の中心は「ZIP を展開しない」こと**（ADR-002）。extract / extractall は
一切呼ばず、ZipInfo のメタデータ検査と、SKILL.md ただ 1 ファイルの
ストリーム読み出しだけで完結させる。ファイルシステムへ書き込む処理が存在
しなければ、path traversal も symlink 攻撃も「成立する先」がない。
"""

from __future__ import annotations

import io
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass, field
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# 例外（呼び出し側が HTTP ステータスへ写像する。ここでは HTTP を知らない）
# ---------------------------------------------------------------------------


class InspectionError(Exception):
    """ZIP 検査に失敗した。message はそのまま利用者へ見せる日本語."""


class InvalidArchiveError(InspectionError):
    """ZIP として壊れている / 危険なエントリを含む → 400."""


class ArchiveTooLargeError(InspectionError):
    """サイズ・ファイル数の上限を超えた → 413."""


class InvalidPackageError(InspectionError):
    """ZIP としては正常だが Skills パッケージの要件を満たさない → 422."""


# ---------------------------------------------------------------------------
# 戻り値
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "size": self.size}


@dataclass(frozen=True)
class SkillPackage:
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    skill_md_path: str = ""
    file_tree: list[FileEntry] = field(default_factory=list)
    total_size: int = 0
    # frontmatter を除いた SKILL.md 本文。検証のためにどのみちメモリへ読んで
    # いるものを渡すだけなので、追加の I/O は発生しない（ADR-007）
    body: str = ""


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

SKILL_MD_FILENAME = "SKILL.md"

# macOS の「アーカイブを作成」が同梱するリソースフォークとメタデータ。
# 利用者が作った覚えのないファイルなので、ファイルツリーの表示からは除く。
# ただし **サイズと件数の集計には含める**（除外してしまうと、そこへ zip bomb を
# 仕込まれたときに上限チェックをすり抜けるため）
_NOISE_PREFIXES = ("__MACOSX/",)
_NOISE_BASENAMES = (".DS_Store",)

# Windows のドライブレター（C: など）。一部の展開実装で traversal になりうる
_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")

# Skill 名に許す文字。制御文字・パス区切り・引用符を弾く。
# ダウンロード時の Content-Disposition ヘッダに載る値なので、改行の混入を
# 名前の検証段階で断っておく（ヘッダインジェクションの予防）
_INVALID_NAME_RE = re.compile(r'[\x00-\x1f\x7f/\\"\']')

MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 2000
MAX_TAG_LENGTH = 100
MAX_TAGS = 20


# ---------------------------------------------------------------------------
# エントリ名の検査
# ---------------------------------------------------------------------------


def is_unsafe_entry_name(name: str) -> bool:
    """展開されれば アーカイブ外へ書き出されうる名前かどうか.

    実際には展開しないので「危険な名前だから壊れる」わけではないが、
    こういう ZIP を保管して社内へ配布すれば、**ダウンロードした人の手元で**
    展開されて被害が出る。中継点としての責任を果たすために弾く。
    """
    if not name or name.strip() == "":
        return True
    # 絶対パス
    if name.startswith("/"):
        return True
    # バックスラッシュ（Windows 形式のパス区切り）。ZIP 仕様上の区切りは "/" のみで、
    # "\" を含む名前は正規の作り方では生まれない
    if "\\" in name:
        return True
    # ドライブレター
    if _DRIVE_LETTER_RE.match(name):
        return True
    # 親ディレクトリ参照。"a/../b" のように中間にあるものも拒否する
    # （正規化して収まれば安全ではあるが、正規の Skills パッケージには現れない）
    parts = name.split("/")
    if any(part == ".." for part in parts):
        return True
    # 正規化した結果がアーカイブ外へ出ていないかの二重確認
    normalized = posixpath.normpath(name)
    return normalized.startswith(("/", "../")) or normalized == ".."


def is_symlink(info: zipfile.ZipInfo) -> bool:
    """symlink エントリかどうか.

    UNIX 由来の ZIP は external_attr の上位 16bit に st_mode が入る。
    Windows で作られた ZIP では 0 になり、その場合は symlink を表現できない
    ので False になる（＝この判定で取りこぼしは起きない）。
    """
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _is_noise(path: str) -> bool:
    if path.startswith(_NOISE_PREFIXES):
        return True
    return posixpath.basename(path) in _NOISE_BASENAMES


# ---------------------------------------------------------------------------
# frontmatter
# ---------------------------------------------------------------------------


def split_frontmatter(text: str) -> tuple[str, str]:
    """SKILL.md を「frontmatter の中身」と「その後ろの本文」に切り分ける.

    `---` で挟まれたブロックを手で切り出す。ファイル全体を YAML として
    読ませないのは、frontmatter の後ろは Markdown 本文であり YAML として
    妥当である保証がないため。

    **本文を frontmatter と分けて取り出すことに意味がある**（ADR-007）。
    frontmatter には name / description がそのまま書かれているので、これを
    本文に含めたまま検索対象にすると「name に当たった Skill は本文にも
    当たったことになる」という常に真の判定が混ざり、ヒット箇所の表示も
    スニペットもメタデータの再掲になってしまう。
    """
    # UTF-8 BOM 付きで保存されているケースがある（先頭が BOM だと "---" 判定に落ちる）
    stripped = text.lstrip("﻿")
    lines = stripped.splitlines()

    if not lines or lines[0].strip() != "---":
        raise InvalidPackageError(
            f"{SKILL_MD_FILENAME} の先頭に YAML frontmatter（--- で挟まれたブロック）がありません。"
        )

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            end_index = index
            break
    if end_index is None:
        raise InvalidPackageError(
            f"{SKILL_MD_FILENAME} の frontmatter が閉じられていません"
            "（--- が 1 つしかありません）。"
        )

    block = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).strip()
    return block, body


def parse_frontmatter(text: str) -> dict[str, Any]:
    """SKILL.md 先頭の YAML frontmatter をマッピングとして読む."""
    block, _ = split_frontmatter(text)
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise InvalidPackageError(
            f"{SKILL_MD_FILENAME} の frontmatter を YAML として解析できません: {exc}"
        ) from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise InvalidPackageError(
            f"{SKILL_MD_FILENAME} の frontmatter は"
            "キーと値の対応（マッピング）である必要があります。"
        )
    return data


def _extract_name(data: dict[str, Any]) -> str:
    raw = data.get("name")
    if raw is None:
        raise InvalidPackageError(f"{SKILL_MD_FILENAME} の frontmatter に name がありません。")
    if not isinstance(raw, str):
        raise InvalidPackageError("name は文字列である必要があります。")
    name = raw.strip()
    if not name:
        raise InvalidPackageError("name が空です。")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidPackageError(f"name が長すぎます（{MAX_NAME_LENGTH} 文字以内）。")
    if _INVALID_NAME_RE.search(name):
        raise InvalidPackageError(
            "name に使用できない文字（制御文字・改行・スラッシュ・引用符）が含まれています。"
        )
    return name


def _extract_description(data: dict[str, Any]) -> str:
    raw = data.get("description")
    if raw is None:
        raise InvalidPackageError(
            f"{SKILL_MD_FILENAME} の frontmatter に description がありません。"
        )
    if not isinstance(raw, str):
        raise InvalidPackageError("description は文字列である必要があります。")
    description = raw.strip()
    if not description:
        raise InvalidPackageError("description が空です。")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise InvalidPackageError(
            f"description が長すぎます（{MAX_DESCRIPTION_LENGTH} 文字以内）。"
        )
    return description


def _extract_tags(data: dict[str, Any]) -> list[str]:
    """tags は任意。無ければ空リスト."""
    raw = data.get("tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        # "a, b" のようにカンマ区切りで書かれることがあるので受け入れる
        candidates = raw.split(",")
    elif isinstance(raw, list):
        candidates = raw
    else:
        raise InvalidPackageError("tags は文字列またはリストである必要があります。")

    tags: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            raise InvalidPackageError("tags の各要素は文字列である必要があります。")
        # 大小文字の違いで別タグが乱立するのを防ぐため小文字へ寄せる
        tag = candidate.strip().lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise InvalidPackageError(f"タグが長すぎます（{MAX_TAG_LENGTH} 文字以内）: {tag}")
        if tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise InvalidPackageError(f"タグが多すぎます（{MAX_TAGS} 個以内）。")
    return tags


# ---------------------------------------------------------------------------
# SKILL.md の位置
# ---------------------------------------------------------------------------


def find_skill_md(paths: list[str]) -> str:
    """SKILL.md を 1 つだけ特定する.

    許すのは「ルート直下」と「1 階層下のディレクトリ直下」の 2 通り。
    深い階層まで探索しないのは、どれが正なのかを機械的に決められないから。
    曖昧なまま最初の 1 件を採用すると、利用者の意図と違うものが登録される。
    """
    candidates = [
        path
        for path in paths
        if posixpath.basename(path) == SKILL_MD_FILENAME and path.count("/") <= 1
    ]
    if not candidates:
        raise InvalidPackageError(
            f"{SKILL_MD_FILENAME} が見つかりません。"
            f"ZIP のルート直下、または 1 階層下のディレクトリ直下に置いてください。"
        )
    if len(candidates) > 1:
        joined = "、".join(sorted(candidates))
        raise InvalidPackageError(
            f"{SKILL_MD_FILENAME} が複数見つかりました（{joined}）。1 つにしてください。"
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# 本体
# ---------------------------------------------------------------------------


def inspect_skill_zip(
    data: bytes,
    *,
    max_total_size: int,
    max_files: int,
    max_skill_md_size: int,
) -> SkillPackage:
    """ZIP を検査し、Skills パッケージのメタデータを返す.

    検査の順序には意味がある。**安価な判定を先に置き、解凍を最後にする**。
    ヘッダを読むだけで弾ける入力に、解凍のコストを払わないため。
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InvalidArchiveError(f"ZIP ファイルとして読み取れません: {exc}") from exc

    with archive as zf:
        file_tree: list[FileEntry] = []
        all_paths: list[str] = []
        total_size = 0
        file_count = 0

        for info in zf.infolist():
            name = info.filename

            # --- 1. 名前の健全性（展開されれば危険な名前）---
            if is_unsafe_entry_name(name):
                raise InvalidArchiveError(
                    f"安全でないパスを含む ZIP です: {name!r}"
                    "（絶対パス・上位ディレクトリ参照・バックスラッシュは受け付けません）"
                )

            # --- 2. symlink ---
            if is_symlink(info):
                raise InvalidArchiveError(
                    f"シンボリックリンクを含む ZIP は受け付けません: {name!r}"
                )

            if info.is_dir():
                continue

            # --- 3. ファイル数の上限 ---
            file_count += 1
            if file_count > max_files:
                raise ArchiveTooLargeError(
                    f"ZIP 内のファイル数が上限（{max_files} 件）を超えています。"
                )

            # --- 4. 展開後サイズの上限 ---
            # ZipInfo.file_size は「展開後のサイズ」をヘッダから読んだ値。
            # 1 バイトも解凍せずに zip bomb を遮断できる。累積が上限を超えた
            # 時点で即座に打ち切り、残りのエントリは見ない
            total_size += info.file_size
            if total_size > max_total_size:
                raise ArchiveTooLargeError(
                    f"展開後の合計サイズが上限（{max_total_size // (1024 * 1024)}MB）を"
                    "超えています。"
                )

            all_paths.append(name)
            if not _is_noise(name):
                file_tree.append(FileEntry(path=name, size=info.file_size))

        # --- 5. SKILL.md の特定 ---
        skill_md_path = find_skill_md(all_paths)

        # --- 6. SKILL.md だけを読む ---
        # ここで初めて解凍が発生する。ヘッダの file_size は攻撃者が偽装できる
        # ので、実際の読み出しにも独立した上限を課す（上限 +1 バイト読んで
        # 超過を検出する）
        with zf.open(skill_md_path) as handle:
            raw = handle.read(max_skill_md_size + 1)
        if len(raw) > max_skill_md_size:
            raise ArchiveTooLargeError(
                f"{SKILL_MD_FILENAME} が大きすぎます（{max_skill_md_size // 1024}KB 以内）。"
            )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidPackageError(f"{SKILL_MD_FILENAME} を UTF-8 として読み取れません。") from exc

    _, body = split_frontmatter(text)
    frontmatter = parse_frontmatter(text)
    return SkillPackage(
        name=_extract_name(frontmatter),
        description=_extract_description(frontmatter),
        tags=_extract_tags(frontmatter),
        skill_md_path=skill_md_path,
        file_tree=file_tree,
        total_size=total_size,
        body=body,
    )
