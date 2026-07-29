"""検索の「当たり方」を決める純粋関数群（ADR-006）.

このモジュールは **FastAPI にも SQLAlchemy にも依存しない**。入力は文字列、
出力は数値・リスト・文字列で、DB もリクエストコンテキストも知らない。
`zip_inspector` と同じ理由でそうしている。

- SQL 側は「どの Skill を返すか」（絞り込み）だけを担当し、
  **「どの順に返すか」と「どこに当たったか」はここが決める**
- 順位の規則を SQL の巨大な CASE 式ではなく Python の関数にしておくと、
  DB を立てずに順位のテストが書ける。件数線形（seq scan）を受け入れている
  現状では、絞り込み済みの行を Python で並べ替えても計算量クラスは変わらない

将来 pg_trgm を入れて SQL 側へスコアリングを移す日が来たときの移行先は
ADR-006 に書いてある。
"""

from __future__ import annotations

# フィールドごとの重み。「トークンが name に当たれば 3 点、description なら 2 点、
# 本文なら 1 点。1 トークンにつき最高点だけを数え、それを全トークン分足す」
# ——順位の規則は一行で説明できる範囲に留める（説明できない順位は苦情の元になる）
SCORE_NAME = 3
SCORE_DESCRIPTION = 2
SCORE_BODY = 1

# フィールド名。API の matched_fields にそのまま出るので、この順序が表示順になる
FIELD_NAME = "name"
FIELD_DESCRIPTION = "description"
FIELD_BODY = "body"

# スニペットのヒット位置から前後に取る文字数
SNIPPET_RADIUS = 40


def tokenize(q: str | None) -> list[str]:
    """検索語を空白で分割する.

    引数なしの `str.split()` は Unicode の空白全般で分割するので、
    全角空白（U+3000）も何もせずに扱える。日本語入力では半角と全角が
    混ざるのが普通なので、ここを取りこぼすと「打ったのに出ない」になる。

    同じ語を 2 回打たれても点数が二重に乗らないよう、重複は落とす
    （順序は保つ。matched_fields / スニペットの決定に効くため）。
    """
    if not q:
        return []
    seen: list[str] = []
    for token in q.split():
        if token not in seen:
            seen.append(token)
    return seen


def _contains(haystack: str, token: str) -> bool:
    """大文字小文字を区別しない部分一致.

    絞り込みは SQL の ILIKE が行うので、ここでの判定は **ILIKE と同じ結果に
    なる必要がある**。ずれると「一覧には出るのにハイライトされない」という
    説明のつかない状態になる。casefold() は lower() より広く畳む
    （ドイツ語の ß など）が、ILIKE との差が出るのは日本語・英語の範囲外なので
    実害はない。
    """
    return token.casefold() in haystack.casefold()


def matched_fields(tokens: list[str], *, name: str, description: str, body: str) -> list[str]:
    """どのフィールドに当たったか。1 つでもトークンが当たれば列挙する."""
    if not tokens:
        return []
    fields: list[str] = []
    for field, text in (
        (FIELD_NAME, name),
        (FIELD_DESCRIPTION, description),
        (FIELD_BODY, body),
    ):
        if any(_contains(text, token) for token in tokens):
            fields.append(field)
    return fields


def score(tokens: list[str], *, name: str, description: str, body: str) -> int:
    """関連度スコア。トークンごとの最高点の合計.

    最高点だけを取るのは、同じ語が name と本文の両方に出ているだけで
    順位が跳ね上がるのを避けるため。「どのフィールドまで当たったか」ではなく
    「一番強いところに当たったか」を見る。
    """
    total = 0
    for token in tokens:
        if _contains(name, token):
            total += SCORE_NAME
        elif _contains(description, token):
            total += SCORE_DESCRIPTION
        elif _contains(body, token):
            total += SCORE_BODY
    return total


def extract_snippet(tokens: list[str], body: str, *, radius: int = SNIPPET_RADIUS) -> str | None:
    """本文ヒット時に、最初のヒット位置の周辺を切り出す.

    「name にも description にも書いていないが本文には書いてある」という
    ヒットは、一覧だけ見ても**なぜこれが出たのか分からない**。その理由を
    その場で示すのがスニペットの役目なので、本文に当たっていないときは
    None を返す（何も説明することがない）。
    """
    if not tokens or not body:
        return None

    folded = body.casefold()
    positions = [
        index for index in (folded.find(token.casefold()) for token in tokens) if index >= 0
    ]
    if not positions:
        return None

    hit = min(positions)
    start = max(0, hit - radius)
    end = min(len(body), hit + radius)
    # 改行をそのまま出すと一覧の行が崩れるので、1 行に畳んでから前後を詰める
    snippet = " ".join(body[start:end].split())
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{snippet}{suffix}"
