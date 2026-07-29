#!/usr/bin/env python
"""検索試験用のデータを **API 経由で** 投入する（`docs/manual-test.md` §3 と対応）.

    docker compose up -d
    cd backend && python3 scripts/seed_search_data.py
    # ポートを変えている場合: python3 scripts/seed_search_data.py http://localhost:8010

標準ライブラリだけで動くので、仮想環境も依存のインストールも要らない。

DB へ直接 INSERT せず `POST /skills` を叩くのは、**シード投入それ自体が
アップロード経路の回帰確認を兼ねる**ため。8 件が 201 で返らなければ、
検索を試すまでもなく登録が壊れている。

## 冪等ではない

同じ名前で再実行すると v2・v3 と版が増えていく（同名再アップロード＝新しい版、
という仕様どおりの挙動）。**やり直したいときは DB ごと作り直す**:

    docker compose down -v && docker compose up -d
    python3 scripts/seed_search_data.py

「消しても 1 コマンドで戻る」状態を保っていることが、Alembic をまだ入れない
根拠でもある（design.md §3 のマイグレーション方針）。

## データの決め方

件数を増やすことではなく、**検索の各性質を 1 つずつ切り分けて確かめられること**
を狙って名前・説明・本文・タグを配置している。どの Skill が何のために居るかは
`SEEDS` の各行のコメントを参照。
"""

from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

DEFAULT_API = "http://localhost:8000"
# API の起動待ち。`docker compose up -d` はコンテナを起動した時点で戻るので、
# その直後にこのスクリプトを叩くと uvicorn がまだ受け付けていないことがある。
# 待たずに落ちると「シードが壊れている」ように見えるが、実際はただ早すぎるだけ
STARTUP_TIMEOUT_SECONDS = 60

# (name, description, tags, body, 何を確かめるために居るか)
SEEDS: list[tuple[str, str, list[str], str, str]] = [
    (
        "mail-digest",
        "受信メールを要約して日次でまとめる",
        ["mail"],
        "# 概要\n\n要約結果は Slack にも投げられる。宛先はチャンネル ID で指定する。\n",
        "本文にだけ slack がある → 最下位に来てスニペットが出ることの確認",
    ),
    (
        "csv-cleaner",
        "CSV を整形して重複行を落とす",
        ["data"],
        "# 使い方\n\n標準ライブラリだけで動く。\n",
        "検索語に当たらない対照（ヒットしないものが混ざらないことの確認）",
    ),
    (
        "reportXbuilder",
        "エスケープ確認の対照。アンダースコアを X に置き換えた名前",
        ["data"],
        "# 本文\n",
        "`report_builder` で検索したときに **これが出ないこと** の確認",
    ),
    (
        "report_builder",
        "定型レポートを組み立てる",
        ["data"],
        "# 本文\n",
        "`_` が 1 文字ワイルドカードとして解釈されないことの確認",
    ),
    (
        "teams-notifier",
        "Microsoft Teams のチャンネルへ通知する",
        ["teams", "notification"],
        "# 使い方\n\nコネクタ URL を発行しておく。\n",
        "複数語 AND で落ちる側（slack を持たない）／タグ AND の対照",
    ),
    (
        "slack-uploader",
        "Slack へファイルを添付して送る",
        ["slack"],
        "# 使い方\n\nファイルサイズの上限に注意。\n",
        "name ヒットの同点相手／複数語 AND で落ちる側（通知を持たない）",
    ),
    (
        "slack-notifier",
        "Slack通知を任意のチャンネルへ送る",
        ["slack", "notification"],
        "# 使い方\n\nWebhook URL を環境変数に設定して実行する。\n",
        "日本語部分一致（通知 → Slack通知）／複数語 AND で唯一残る／本文ヒット webhook",
    ),
    (
        "xss-check",
        "本文に script タグを含む（表示の検証用）",
        ["misc"],
        (
            "# XSS 検証\n\n"
            "<script>alert(1)</script>\n\n"
            "上の行が **タグごと文字として見えていれば正しい**。"
            "アラートが出たり、行が消えていたら異常。\n"
        ),
        "詳細ページで生 HTML がテキストとして表示されることの確認（ADR-007）",
    ),
]


def build_zip(name: str, description: str, tags: list[str], body: str) -> bytes:
    """1 階層下に SKILL.md を置いた、実際の配布形に近い ZIP を作る."""
    skill_md = (
        f"---\nname: {name}\ndescription: {description}\ntags: [{', '.join(tags)}]\n---\n\n{body}"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{name}/SKILL.md", skill_md)
    return buffer.getvalue()


def upload(api: str, data: bytes) -> tuple[int, dict]:
    """multipart/form-data で POST する（標準ライブラリだけで済ませる）."""
    boundary = uuid.uuid4().hex
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="skill.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )

    request = urllib.request.Request(
        f"{api}/skills",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def wait_for_api(api: str) -> bool:
    """`/health` が 200 を返すまで待つ（DB 接続まで確認されている）."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{api}/health", timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main() -> int:
    api = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_API).rstrip("/")
    print(f"投入先: {api}\n")

    if not wait_for_api(api):
        print(
            f"{api}/health に {STARTUP_TIMEOUT_SECONDS} 秒待っても繋がりませんでした。"
            "\n\n確認すること:"
            "\n  1. `docker compose ps` で backend が起動しているか"
            "\n  2. 8000 番が他のプロジェクトに取られていないか。取られている場合は"
            "\n     ポートをずらして起動し、この URL も合わせる:"
            "\n       BACKEND_PORT=8010 FRONTEND_PORT=3010 docker compose up -d"
            "\n       python3 scripts/seed_search_data.py http://localhost:8010"
        )
        return 1

    failed = 0
    for name, description, tags, body, purpose in SEEDS:
        status, result = upload(api, build_zip(name, description, tags, body))
        if status == 201:
            print(f"  201 {name:<16} v{result['version']}  — {purpose}")
        else:
            failed += 1
            print(f"  {status} {name:<16} 失敗: {result.get('detail')}")

    if failed:
        print(f"\n{failed} 件が失敗しました。API が起動しているか確認してください。")
        return 1

    print(
        f"\n{len(SEEDS)} 件を投入しました。"
        "\n期待する検索結果（順序・件数つき）は docs/manual-test.md §3 にあります。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
