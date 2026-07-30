"""設定と設計ドキュメントのパリティ検証（DB 不要）.

`docs/design.md` §7 の環境変数表が `Settings` から遅れないようにする。
`MAX_SKILL_MD_SIZE` が表から漏れていたのは「§7 に何を載せるかの基準が
無かった」ことの帰結だったので、基準（全フィールドを載せる）を
メモではなくテストで強制する（ADR-008 論点 D / learnings.md #9）。
"""

from pathlib import Path

import pytest

from app.core.config import Settings

DESIGN_DOC = Path(__file__).parents[2] / "docs" / "design.md"


def _design_text() -> str:
    return DESIGN_DOC.read_text(encoding="utf-8")


def test_design_mdが読める():
    """パスがずれていたら以降のテストが無意味に緑になるので先に確かめる."""
    assert DESIGN_DOC.is_file(), f"design.md が見つからない: {DESIGN_DOC}"
    assert "## 7. 設定（環境変数）" in _design_text()


@pytest.mark.parametrize("field_name", sorted(Settings.model_fields))
def test_Settingsの全フィールドがdesign_mdに載っている(field_name: str):
    """フィールドを足したらこのテストが落ちる。§7 に行を足せば通る（それが仕様）."""
    env_var = field_name.upper()
    assert env_var in _design_text(), (
        f"`{env_var}` が docs/design.md に無い。"
        "§7 の環境変数表は Settings 全フィールドと 1:1 対応する規則（ADR-008）。"
    )
