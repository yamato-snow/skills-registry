#!/usr/bin/env python
"""手動テスト用の ZIP を生成する（`docs/manual-test.md` §2 と 1:1 対応）.

    cd backend && uv run python scripts/make_test_zips.py

出力先はリポジトリ直下の `manual-test/zips/`（`.gitignore` 済み）。

**危険な ZIP をリポジトリに同梱しない**方針は `tests/helpers.py` と同じで、
そこのヘルパーをそのまま import している。

- path traversal や symlink を含む ZIP をリポジトリに置くと、クローンした人の
  手元で誤って展開される事故につながる（ADR-002 の帰結）
- バイナリのフィクスチャは中身が読めず、レビューで「これは何を検証するのか」が
  分からない。生成コードなら差分で意図が伝わる

同じ理由で、自動テストと手動テストが**同一のヘルパーから同じ入力を作る**ことにも
意味がある。手で確かめている ZIP と CI が食わせている ZIP が別物だと、
片方だけ通る状態に気づけない。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
# スクリプトとして直接起動されると sys.path[0] が scripts/ になるので、
# tests.helpers を import できるよう backend/ を通す
sys.path.insert(0, str(BACKEND_DIR))

from tests.helpers import (  # noqa: E402  (sys.path を通したあとに import する必要がある)
    DEFAULT_SKILL_MD,
    build_skill_md,
    make_skill_zip,
    make_zip,
    make_zip_bomb,
    make_zip_with_many_files,
    make_zip_with_raw_entries,
)

OUTPUT_DIR = REPO_ROOT / "manual-test" / "zips"

# 01 と 04 は同じ name を使う。同名の再アップロードが「新規 Skill」ではなく
# 「新しい版」になることを画面で確かめるため
NORMAL_NAME = "mt-normal"


def _huge_skill_md() -> str:
    """SKILL.md 単体が 1MB を超えるもの（`max_skill_md_size` 超過）."""
    # 本文を 1MB 強まで膨らませる。ZIP 全体のサイズ上限（50MB）ではなく
    # SKILL.md 単体の上限に当てたいので、他のファイルは入れない
    return build_skill_md("mt-huge", "SKILL.md が大きすぎる", body="あ" * (1024 * 1024))


def _not_utf8_skill_md() -> bytes:
    """UTF-8 として読めない SKILL.md（Shift_JIS で書かれた場合を模す）."""
    return build_skill_md("mt-sjis", "文字コードが UTF-8 でない").encode("shift_jis")


# (連番, ファイル名, 中身, 期待結果) — docs/manual-test.md §2 の表と同じ順序・同じ番号
CASES: list[tuple[str, str, bytes, str]] = [
    (
        "01",
        "01_normal_root.zip",
        make_skill_zip(
            skill_md=build_skill_md(NORMAL_NAME, "ルート直下に SKILL.md がある正常系", ["sample"]),
            extra={"scripts/run.sh": "echo hi\n"},
        ),
        "201・一覧に出る",
    ),
    (
        "02",
        "02_normal_nested.zip",
        make_skill_zip(
            skill_md=build_skill_md("mt-nested", "1 階層下に SKILL.md がある正常系", ["sample"]),
            skill_md_path="mt-nested/SKILL.md",
        ),
        "201",
    ),
    (
        "03",
        "03_no_tags.zip",
        make_skill_zip(skill_md=build_skill_md("mt-no-tags", "tags を書いていない")),
        "201・タグ表示なし",
    ),
    (
        "04",
        "04_reupload.zip",
        make_skill_zip(
            skill_md=build_skill_md(NORMAL_NAME, "01 の説明を書き換えた版", ["sample", "updated"])
        ),
        "201・v2 になる（新規 Skill にならない）",
    ),
    ("05", "05_not_a_zip.zip", "これは ZIP ではありません".encode(), "400"),
    (
        "06",
        "06_path_traversal.zip",
        make_zip_with_raw_entries({"SKILL.md": DEFAULT_SKILL_MD, "../../evil.sh": "rm -rf /"}),
        "400",
    ),
    (
        "07",
        "07_symlink.zip",
        make_zip_with_raw_entries(
            {"SKILL.md": DEFAULT_SKILL_MD}, symlinks={"secret": "/etc/shadow"}
        ),
        "400",
    ),
    (
        "08",
        "08_backslash.zip",
        make_zip_with_raw_entries({"SKILL.md": DEFAULT_SKILL_MD, "..\\..\\x": "payload"}),
        "400",
    ),
    ("09", "09_too_many_files.zip", make_zip_with_many_files(500), "413（501 ファイル）"),
    ("10", "10_zip_bomb.zip", make_zip_bomb(60 * 1024 * 1024), "413（一瞬で拒否される）"),
    ("11", "11_no_skill_md.zip", make_zip({"README.md": "SKILL.md がない"}), "422"),
    (
        "12",
        "12_multiple_skill_md.zip",
        make_zip({"SKILL.md": DEFAULT_SKILL_MD, "sub/SKILL.md": DEFAULT_SKILL_MD}),
        "422",
    ),
    (
        "13",
        "13_bad_frontmatter.zip",
        make_zip({"SKILL.md": "---\ndescription: name が無い\n---\n\n# 本文\n"}),
        "422",
    ),
    ("14", "14_not_utf8.zip", make_zip({"SKILL.md": _not_utf8_skill_md()}), "422"),
    ("15", "15_huge_skill_md.zip", make_zip({"SKILL.md": _huge_skill_md()}), "413"),
    (
        "16",
        "16_macosx_junk.zip",
        make_zip(
            {
                "SKILL.md": build_skill_md("mt-macosx", "macOS の付随ファイル入り", ["sample"]),
                "__MACOSX/._SKILL.md": "resource fork",
                ".DS_Store": "finder metadata",
            }
        ),
        "201・__MACOSX と .DS_Store はファイル構成に出ない",
    ),
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"出力先: {OUTPUT_DIR}\n")
    print(f"{'No':<4}{'ファイル名':<26}{'サイズ':>10}  期待結果")
    print("-" * 78)
    for number, filename, data, expected in CASES:
        (OUTPUT_DIR / filename).write_bytes(data)
        print(f"{number:<4}{filename:<26}{len(data):>9,}B  {expected}")

    print(
        f"\n{len(CASES)} 件を生成しました。"
        "\n手順と判定欄は docs/manual-test.md §2 にあります。"
        "\n※ 06 / 07 / 08 は意図的に危険なエントリを含みます。**展開しないでください**"
        "（画面へアップロードして拒否されることを確かめるためのものです）。"
    )


if __name__ == "__main__":
    main()
