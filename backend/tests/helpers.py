"""テスト用の ZIP 生成ヘルパー.

**フィクスチャの ZIP をリポジトリに同梱しない**方針を取っている。

理由は 2 つ。
1. path traversal や symlink を含む「危険な ZIP」をリポジトリに置きたくない。
   クローンした人の手元で誤って展開される事故を避ける
2. バイナリのフィクスチャは中身が読めず、レビューで「このテストは何を
   検証しているのか」が分からなくなる。生成コードなら差分で意図が伝わる

危険なエントリは zipfile の通常 API（`write` / `writestr` にパスを渡す方法）では
作れないことがあるため、`ZipInfo` を直接組み立てて `writestr` する。
"""

from __future__ import annotations

import io
import stat
import zipfile

DEFAULT_SKILL_MD = """---
name: sample-skill
description: テスト用のサンプル Skill
tags: [sample, test]
---

# sample-skill

使い方の説明。
"""


def build_skill_md(
    name: str = "sample-skill",
    description: str = "テスト用のサンプル Skill",
    tags: list[str] | None = None,
) -> str:
    lines = ["---", f"name: {name}", f"description: {description}"]
    if tags is not None:
        lines.append(f"tags: [{', '.join(tags)}]")
    lines += ["---", "", "# 本文", ""]
    return "\n".join(lines)


def make_zip(entries: dict[str, str | bytes]) -> bytes:
    """普通の ZIP を作る（安全なエントリのみ）."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in entries.items():
            zf.writestr(path, content)
    return buffer.getvalue()


def make_skill_zip(
    *,
    skill_md: str | None = DEFAULT_SKILL_MD,
    skill_md_path: str = "SKILL.md",
    extra: dict[str, str | bytes] | None = None,
) -> bytes:
    """正常系の Skills パッケージ."""
    entries: dict[str, str | bytes] = {}
    if skill_md is not None:
        entries[skill_md_path] = skill_md
    entries.update(extra or {})
    return make_zip(entries)


def make_zip_with_raw_entries(
    entries: dict[str, str | bytes],
    *,
    symlinks: dict[str, str] | None = None,
) -> bytes:
    """ZipInfo を直接組み立てる版.

    `../../evil.sh` のような名前も、`writestr` に ZipInfo を渡せばそのまま
    書き込める（パスの正規化が入らない）。symlink は external_attr の
    上位 16bit に S_IFLNK を立て、中身にリンク先の文字列を入れて表現する。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in entries.items():
            info = zipfile.ZipInfo(path)
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            zf.writestr(info, content)
        for path, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(path)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, target)
    return buffer.getvalue()


def make_zip_bomb(uncompressed_size: int) -> bytes:
    """展開後サイズが大きい ZIP.

    ゼロ埋めなので圧縮率が極端に高く、生成物は数十 KB に収まる。
    「ヘッダを読むだけで、解凍せずに遮断できる」ことを確かめるためのケース。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", DEFAULT_SKILL_MD)
        zf.writestr("payload.bin", b"\0" * uncompressed_size)
    return buffer.getvalue()


def make_zip_with_many_files(count: int) -> bytes:
    entries: dict[str, str | bytes] = {"SKILL.md": DEFAULT_SKILL_MD}
    for index in range(count):
        entries[f"files/f{index:05d}.txt"] = "x"
    return make_zip(entries)
