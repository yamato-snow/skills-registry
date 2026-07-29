"""zip_inspector の単体テスト.

このモジュールはセキュリティ境界そのものなので、検証項目 1 つにつき
テスト 1 つを対応させる（ADR-002 の検証項目一覧がそのままテスト名になる）。
"""

import pytest

from app.services.zip_inspector import (
    ArchiveTooLargeError,
    InvalidArchiveError,
    InvalidPackageError,
    inspect_skill_zip,
    is_symlink,
    is_unsafe_entry_name,
    parse_frontmatter,
)
from tests.helpers import (
    DEFAULT_SKILL_MD,
    build_skill_md,
    make_skill_zip,
    make_zip,
    make_zip_bomb,
    make_zip_with_many_files,
    make_zip_with_raw_entries,
)

LIMITS = {
    "max_total_size": 50 * 1024 * 1024,
    "max_files": 500,
    "max_skill_md_size": 1024 * 1024,
}


def inspect(data: bytes, **overrides):
    return inspect_skill_zip(data, **{**LIMITS, **overrides})


# ---------------------------------------------------------------------------
# 正常系
# ---------------------------------------------------------------------------


def test_ルート直下のSKILL_mdを読み取れる():
    package = inspect(make_skill_zip(extra={"scripts/run.sh": "echo hi"}))

    assert package.name == "sample-skill"
    assert package.description == "テスト用のサンプル Skill"
    assert package.tags == ["sample", "test"]
    assert package.skill_md_path == "SKILL.md"
    assert {entry.path for entry in package.file_tree} == {"SKILL.md", "scripts/run.sh"}


def test_1階層下のSKILL_mdも読み取れる():
    package = inspect(
        make_skill_zip(skill_md_path="my-skill/SKILL.md", extra={"my-skill/run.sh": "x"})
    )
    assert package.skill_md_path == "my-skill/SKILL.md"


def test_2階層下のSKILL_mdは見つけない():
    """深く探索しないのは、どれが正か機械的に決められないため."""
    with pytest.raises(InvalidPackageError, match="見つかりません"):
        inspect(make_skill_zip(skill_md_path="a/b/SKILL.md"))


def test_tagsは省略できる():
    package = inspect(make_skill_zip(skill_md=build_skill_md(tags=None)))
    assert package.tags == []


def test_macOSのメタデータはファイルツリーから除外される():
    data = make_zip(
        {
            "SKILL.md": DEFAULT_SKILL_MD,
            "__MACOSX/._SKILL.md": "\x00\x01",
            ".DS_Store": "\x00",
        }
    )
    package = inspect(data)
    assert [entry.path for entry in package.file_tree] == ["SKILL.md"]
    # 除外するのは表示だけで、集計には含める（そこへ bomb を仕込まれないため）
    assert package.total_size > len(DEFAULT_SKILL_MD.encode())


def test_BOM付きのSKILL_mdも読める():
    package = inspect(make_skill_zip(skill_md="\ufeff" + DEFAULT_SKILL_MD))
    assert package.name == "sample-skill"


# ---------------------------------------------------------------------------
# 必須ケース 1: 壊れた ZIP
# ---------------------------------------------------------------------------


def test_ZIPでないバイト列は拒否する():
    with pytest.raises(InvalidArchiveError, match="読み取れません"):
        inspect(b"this is not a zip file")


# ---------------------------------------------------------------------------
# 必須ケース 2: SKILL.md 欠落・重複
# ---------------------------------------------------------------------------


def test_SKILL_mdがなければ拒否する():
    with pytest.raises(InvalidPackageError, match="見つかりません"):
        inspect(make_skill_zip(skill_md=None, extra={"README.md": "hello"}))


def test_SKILL_mdが複数あれば拒否する():
    """どちらを正とするか決められないので、勝手に選ばず利用者へ返す."""
    data = make_zip({"SKILL.md": DEFAULT_SKILL_MD, "pkg/SKILL.md": DEFAULT_SKILL_MD})
    with pytest.raises(InvalidPackageError, match="複数"):
        inspect(data)


def test_空のZIPは拒否する():
    with pytest.raises(InvalidPackageError):
        inspect(make_zip({}))


# ---------------------------------------------------------------------------
# 必須ケース 3: path traversal と危険なエントリ
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evil_path",
    [
        "../../etc/cron.d/evil",  # 上位ディレクトリ参照
        "pkg/../../evil.sh",  # 中間に .. がある
        "/etc/passwd",  # 絶対パス
        "..\\..\\evil.bat",  # Windows 形式のバックスラッシュ
        "C:/Windows/system32/evil.dll",  # ドライブレター
    ],
)
def test_危険なパスを含むZIPを拒否する(evil_path: str):
    data = make_zip_with_raw_entries({"SKILL.md": DEFAULT_SKILL_MD, evil_path: "payload"})
    with pytest.raises(InvalidArchiveError, match="安全でないパス"):
        inspect(data)


def test_symlinkを含むZIPを拒否する():
    data = make_zip_with_raw_entries(
        {"SKILL.md": DEFAULT_SKILL_MD},
        symlinks={"secret": "/etc/shadow"},
    )
    with pytest.raises(InvalidArchiveError, match="シンボリックリンク"):
        inspect(data)


@pytest.mark.parametrize(
    "name",
    ["", "   ", "/abs", "a\\b", "C:/x", "../x", "a/../../x", ".."],
)
def test_is_unsafe_entry_nameが危険な名前を検出する(name: str):
    assert is_unsafe_entry_name(name) is True


@pytest.mark.parametrize("name", ["SKILL.md", "pkg/SKILL.md", "a/b/c.txt", "./a.txt"])
def test_is_unsafe_entry_nameが正常な名前を通す(name: str):
    assert is_unsafe_entry_name(name) is False


def test_is_symlinkはWindows製ZIPで誤検出しない():
    """external_attr が 0 の場合（Windows 由来）は symlink を表現できない."""
    import zipfile

    info = zipfile.ZipInfo("a.txt")
    info.external_attr = 0
    assert is_symlink(info) is False


# ---------------------------------------------------------------------------
# 必須ケース 4: サイズ・件数の上限
# ---------------------------------------------------------------------------


def test_展開後サイズの上限を超えるZIPを拒否する():
    """生成物は数十 KB だが、ヘッダ上の展開後サイズは上限を超える（zip bomb）."""
    data = make_zip_bomb(uncompressed_size=2 * 1024 * 1024)
    assert len(data) < 100 * 1024  # 圧縮後は小さい ＝ 解凍せずに弾けている証拠

    with pytest.raises(ArchiveTooLargeError, match="合計サイズ"):
        inspect(data, max_total_size=1024 * 1024)


def test_ファイル数の上限を超えるZIPを拒否する():
    with pytest.raises(ArchiveTooLargeError, match="ファイル数"):
        inspect(make_zip_with_many_files(11), max_files=10)


def test_SKILL_mdが大きすぎる場合は拒否する():
    big = DEFAULT_SKILL_MD + "x" * 5000
    with pytest.raises(ArchiveTooLargeError, match="SKILL.md"):
        inspect(make_skill_zip(skill_md=big), max_skill_md_size=1000)


# ---------------------------------------------------------------------------
# frontmatter
# ---------------------------------------------------------------------------


def test_frontmatterがなければ拒否する():
    with pytest.raises(InvalidPackageError, match="frontmatter"):
        inspect(make_skill_zip(skill_md="# 見出しだけの Markdown"))


def test_frontmatterが閉じていなければ拒否する():
    with pytest.raises(InvalidPackageError, match="閉じられていません"):
        inspect(make_skill_zip(skill_md="---\nname: x\ndescription: y\n"))


def test_frontmatterがYAMLとして壊れていれば拒否する():
    with pytest.raises(InvalidPackageError, match="YAML"):
        inspect(make_skill_zip(skill_md="---\nname: [unclosed\n---\n"))


def test_frontmatterがマッピングでなければ拒否する():
    with pytest.raises(InvalidPackageError, match="マッピング"):
        inspect(make_skill_zip(skill_md="---\n- a\n- b\n---\n"))


def test_空のfrontmatterはnameなしとして扱う():
    with pytest.raises(InvalidPackageError, match="name"):
        inspect(make_skill_zip(skill_md="---\n---\n本文"))


@pytest.mark.parametrize(
    ("skill_md", "expected"),
    [
        ("---\ndescription: d\n---\n", "name"),
        ("---\nname: n\n---\n", "description"),
        ("---\nname: '  '\ndescription: d\n---\n", "name が空"),
        ("---\nname: n\ndescription: '  '\n---\n", "description が空"),
        ("---\nname: 123\ndescription: d\n---\n", "name は文字列"),
        ("---\nname: n\ndescription: 123\n---\n", "description は文字列"),
    ],
)
def test_必須項目の不備を日本語で伝える(skill_md: str, expected: str):
    with pytest.raises(InvalidPackageError, match=expected):
        inspect(make_skill_zip(skill_md=skill_md))


def test_nameに改行が入っていれば拒否する():
    """ダウンロード時のヘッダに載る値なので、ここで断つ（ヘッダインジェクション予防）."""
    with pytest.raises(InvalidPackageError, match="使用できない文字"):
        inspect(make_skill_zip(skill_md='---\nname: "a\\nb"\ndescription: d\n---\n'))


def test_nameが長すぎれば拒否する():
    long_name = "a" * 300
    with pytest.raises(InvalidPackageError, match="長すぎます"):
        inspect(make_skill_zip(skill_md=f"---\nname: {long_name}\ndescription: d\n---\n"))


def test_descriptionが長すぎれば拒否する():
    with pytest.raises(InvalidPackageError, match="description が長すぎます"):
        inspect(make_skill_zip(skill_md=f"---\nname: n\ndescription: {'あ' * 2500}\n---\n"))


def test_tagsは小文字化して重複を除く():
    package = inspect(make_skill_zip(skill_md=build_skill_md(tags=["Slack", "slack", "通知"])))
    assert package.tags == ["slack", "通知"]


def test_tagsの空要素は無視する():
    package = inspect(make_skill_zip(skill_md="---\nname: n\ndescription: d\ntags: a, , b\n---\n"))
    assert package.tags == ["a", "b"]


def test_ディレクトリエントリはファイルとして数えない():
    """ZIP にはディレクトリを表すエントリが入ることがある（サイズ 0）."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("pkg/", "")  # ディレクトリエントリ
        zf.writestr("pkg/SKILL.md", DEFAULT_SKILL_MD)
    package = inspect(buffer.getvalue())

    assert [entry.path for entry in package.file_tree] == ["pkg/SKILL.md"]


def test_tagsはカンマ区切りの文字列でも受け付ける():
    package = inspect(make_skill_zip(skill_md="---\nname: n\ndescription: d\ntags: a, b\n---\n"))
    assert package.tags == ["a", "b"]


def test_tagsが不正な型なら拒否する():
    with pytest.raises(InvalidPackageError, match="tags は文字列またはリスト"):
        inspect(make_skill_zip(skill_md="---\nname: n\ndescription: d\ntags: 1\n---\n"))


def test_tagsの要素が文字列でなければ拒否する():
    with pytest.raises(InvalidPackageError, match="tags の各要素"):
        inspect(make_skill_zip(skill_md="---\nname: n\ndescription: d\ntags: [1, 2]\n---\n"))


def test_tagsが長すぎれば拒否する():
    long_tag = "t" * 200
    with pytest.raises(InvalidPackageError, match="タグが長すぎます"):
        inspect(make_skill_zip(skill_md=build_skill_md(tags=[long_tag])))


def test_tagsが多すぎれば拒否する():
    tags = [f"t{i}" for i in range(30)]
    with pytest.raises(InvalidPackageError, match="タグが多すぎます"):
        inspect(make_skill_zip(skill_md=build_skill_md(tags=tags)))


def test_SKILL_mdがUTF_8でなければ拒否する():
    data = make_zip({"SKILL.md": "---\nname: n\ndescription: あ\n---\n".encode("shift_jis")})
    with pytest.raises(InvalidPackageError, match="UTF-8"):
        inspect(data)


def test_parse_frontmatterは三点リーダでも閉じられる():
    """YAML の文書終端記号（...）も終わりとして扱う."""
    data = parse_frontmatter("---\nname: n\n...\n本文")
    assert data == {"name": "n"}
