"""検索の当たり方を決める純粋関数の単体テスト（ADR-006）.

DB を立てずに順位・ヒット箇所・スニペットを検証できるのが、スコアリングを
SQL の CASE 式ではなく Python に置いた理由そのものなので、ここは DB に
依存しないまま保つ。
"""

from __future__ import annotations

from app.services import search

# 3 フィールドをまとめて渡す定型。テスト本文を条件のほうへ寄せる
FIELDS = {
    "name": "slack-notifier",
    "description": "Slack へ通知を送る",
    "body": "---\nname: slack-notifier\n---\n\n# 使い方\n\nWebhook URL を設定して実行する。\n",
}


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------


def test_半角空白で分割される():
    assert search.tokenize("slack 通知") == ["slack", "通知"]


def test_全角空白でも分割される():
    """日本語入力では全角空白が混ざる。ここを落とすと「打ったのに出ない」になる."""
    assert search.tokenize("slack　通知") == ["slack", "通知"]


def test_連続した空白や前後の空白は無視される():
    assert search.tokenize("  slack 　 通知  ") == ["slack", "通知"]


def test_同じ語の重複は落ちる():
    """同じ語を 2 回打っただけで点数が二重に乗らないようにする."""
    assert search.tokenize("slack slack 通知") == ["slack", "通知"]


def test_空やNoneは空リスト():
    assert search.tokenize("") == []
    assert search.tokenize(None) == []
    assert search.tokenize("   ") == []


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def test_nameヒットがdescriptionヒットより高い():
    name_hit = search.score(["slack"], name="slack-notifier", description="通知", body="")
    desc_hit = search.score(["slack"], name="notifier", description="slack へ通知", body="")
    assert name_hit > desc_hit


def test_descriptionヒットが本文ヒットより高い():
    desc_hit = search.score(["webhook"], name="notifier", description="webhook を叩く", body="")
    body_hit = search.score(["webhook"], name="notifier", description="通知", body="webhook URL")
    assert desc_hit > body_hit


def test_トークンごとに最高点だけを数える():
    """name と本文の両方に出ていても、name の 3 点だけ."""
    assert search.score(["slack"], name="slack", description="", body="slack slack") == (
        search.SCORE_NAME
    )


def test_複数トークンの点は合算される():
    score = search.score(["slack", "webhook"], **FIELDS)
    assert score == search.SCORE_NAME + search.SCORE_BODY


def test_当たらなければ0点():
    assert search.score(["存在しない"], **FIELDS) == 0


def test_大文字小文字を区別しない():
    """SQL 側の ILIKE と結果が一致していないと、出るのに光らない状態になる."""
    assert search.score(["SLACK"], **FIELDS) == search.SCORE_NAME


# ---------------------------------------------------------------------------
# matched_fields
# ---------------------------------------------------------------------------


def test_当たったフィールドが列挙される():
    assert search.matched_fields(["slack"], **FIELDS) == ["name", "description", "body"]


def test_本文だけに当たった場合はbodyだけ():
    assert search.matched_fields(["webhook"], **FIELDS) == ["body"]


def test_トークンが無ければ空():
    assert search.matched_fields([], **FIELDS) == []


# ---------------------------------------------------------------------------
# extract_snippet
# ---------------------------------------------------------------------------


def test_本文ヒットの周辺が切り出される():
    body = "あ" * 100 + "webhook" + "い" * 100
    snippet = search.extract_snippet(["webhook"], body)
    assert snippet is not None
    assert "webhook" in snippet
    # 前後が省略されていることが分かる
    assert snippet.startswith("…") and snippet.endswith("…")


def test_本文に当たらなければNone():
    """説明することが無いときに空文字を返すと、画面側で分岐が増える."""
    assert search.extract_snippet(["slack"], "本文には出てこない") is None
    assert search.extract_snippet([], FIELDS["body"]) is None
    assert search.extract_snippet(["slack"], "") is None


def test_改行は1行に畳まれる():
    """一覧の行が崩れないようにする."""
    snippet = search.extract_snippet(["使い方"], FIELDS["body"])
    assert snippet is not None
    assert "\n" not in snippet


def test_最初に当たった位置を採る():
    """複数トークンが当たったときは、本文の前のほうを見せる."""
    body = "さきに-alpha-" + "x" * 200 + "-beta-"
    snippet = search.extract_snippet(["beta", "alpha"], body)
    assert snippet is not None
    assert "alpha" in snippet and "beta" not in snippet


def test_短い本文では省略記号が付かない():
    assert search.extract_snippet(["短い"], "短い本文") == "短い本文"
