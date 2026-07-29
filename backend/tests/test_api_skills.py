"""API の結合テスト（実 PostgreSQL を使う）."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import database_reachable
from tests.helpers import (
    DEFAULT_SKILL_MD,
    build_skill_md,
    make_skill_zip,
    make_zip,
    make_zip_bomb,
    make_zip_with_raw_entries,
)

if not database_reachable():  # pragma: no cover - 環境依存の分岐
    pytest.skip(
        "PostgreSQL に接続できないため API テストをスキップします"
        "（`docker compose up -d db` で起動できます）",
        allow_module_level=True,
    )


def upload_files(data: bytes, filename: str = "skill.zip") -> dict:
    return {"file": (filename, data, "application/zip")}


async def upload(client: AsyncClient, data: bytes):
    return await client.post("/skills", files=upload_files(data))


# ---------------------------------------------------------------------------
# 正常系: 登録 → 検索 → 詳細 → ダウンロード
# ---------------------------------------------------------------------------


async def test_登録から取得までの一連が動く(client: AsyncClient):
    raw = make_skill_zip(extra={"scripts/run.sh": "echo hi"})

    created = await upload(client, raw)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "sample-skill"
    assert body["version"] == 1
    assert body["created"] is True
    skill_id = body["id"]

    listed = await client.get("/skills")
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["sample-skill"]
    assert listed.json()[0]["latest_version"] == 1
    assert listed.json()[0]["tags"] == ["sample", "test"]

    detail = await client.get(f"/skills/{skill_id}")
    assert detail.status_code == 200
    assert {entry["path"] for entry in detail.json()["file_tree"]} == {
        "SKILL.md",
        "scripts/run.sh",
    }
    assert [v["version"] for v in detail.json()["versions"]] == [1]

    downloaded = await client.get(f"/skills/{skill_id}/download")
    assert downloaded.status_code == 200
    # ダウンロードした ZIP が原本と 1 バイトも違わないこと
    assert downloaded.content == raw
    assert "attachment" in downloaded.headers["content-disposition"]


async def test_同名の再アップロードは新しい版になる(client: AsyncClient):
    first = await upload(client, make_skill_zip())
    assert first.json()["version"] == 1

    updated = make_skill_zip(
        skill_md=build_skill_md(description="説明を更新した", tags=["updated"])
    )
    second = await upload(client, updated)
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert second.json()["created"] is False
    # 新規 Skill は増えていない
    assert second.json()["id"] == first.json()["id"]

    skill_id = first.json()["id"]
    detail = (await client.get(f"/skills/{skill_id}")).json()
    # 一覧・詳細に出る説明とタグは最新版のもの
    assert detail["description"] == "説明を更新した"
    assert detail["tags"] == ["updated"]
    # 版履歴は新しい順
    assert [v["version"] for v in detail["versions"]] == [2, 1]


async def test_旧版を指定してダウンロードできる(client: AsyncClient):
    original = make_skill_zip()
    await upload(client, original)
    updated = make_skill_zip(skill_md=build_skill_md(description="v2"))
    response = await upload(client, updated)
    skill_id = response.json()["id"]

    v1 = await client.get(f"/skills/{skill_id}/download", params={"version": 1})
    assert v1.content == original
    v2 = await client.get(f"/skills/{skill_id}/download")
    assert v2.content == updated


# ---------------------------------------------------------------------------
# 検索
# ---------------------------------------------------------------------------


async def test_検索とタグ絞り込みが効く(client: AsyncClient):
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("slack-notifier", "Slack へ通知する", ["slack"])),
    )
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("csv-cleaner", "CSV を整形する", ["data"])),
    )

    # name への部分一致
    assert [s["name"] for s in (await client.get("/skills", params={"q": "slack"})).json()] == [
        "slack-notifier"
    ]
    # description への部分一致（日本語の部分一致が効くことが ILIKE 採用の理由）
    assert [s["name"] for s in (await client.get("/skills", params={"q": "整形"})).json()] == [
        "csv-cleaner"
    ]
    # 大文字小文字を区別しない
    assert len((await client.get("/skills", params={"q": "SLACK"})).json()) == 1
    # タグの完全一致
    assert [s["name"] for s in (await client.get("/skills", params={"tag": "data"})).json()] == [
        "csv-cleaner"
    ]
    # 該当なし
    assert (await client.get("/skills", params={"q": "存在しない"})).json() == []


async def test_検索語のワイルドカードはエスケープされる(client: AsyncClient):
    """`%` を渡しても全件マッチにならない（ADR-004）."""
    await upload(client, make_skill_zip(skill_md=build_skill_md("plain-skill", "説明")))
    assert (await client.get("/skills", params={"q": "%"})).json() == []


async def test_本文が検索対象になりスニペットが返る(client: AsyncClient):
    """description に無くても本文にあれば見つかる（ADR-007）."""
    await upload(
        client,
        make_skill_zip(
            skill_md=build_skill_md(
                "notifier", "通知を送る", ["slack"], body="# 使い方\n\nWebhook URL を設定する。"
            )
        ),
    )

    found = (await client.get("/skills", params={"q": "webhook"})).json()
    assert [s["name"] for s in found] == ["notifier"]
    assert found[0]["matched_fields"] == ["body"]
    # なぜ当たったのかが一覧のその場で分かる
    assert "Webhook" in found[0]["snippet"]


async def test_qが無ければmatched_fieldsもスニペットも空(client: AsyncClient):
    await upload(client, make_skill_zip())
    item = (await client.get("/skills")).json()[0]
    assert item["matched_fields"] == []
    assert item["snippet"] is None


async def test_複数語はANDで効く(client: AsyncClient):
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("slack-notifier", "Slack へ通知する", ["slack"])),
    )
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("slack-uploader", "Slack へ添付を送る", ["slack"])),
    )

    # 片方の語しか持たない Skill は落ちる
    both = (await client.get("/skills", params={"q": "slack 通知"})).json()
    assert [s["name"] for s in both] == ["slack-notifier"]
    # 全角空白でも同じ結果になる
    zenkaku = (await client.get("/skills", params={"q": "slack　通知"})).json()
    assert [s["name"] for s in zenkaku] == ["slack-notifier"]
    # どちらも当たらない語を足すと 0 件
    assert (await client.get("/skills", params={"q": "slack 存在しない"})).json() == []


async def test_q指定時は関連度順に並ぶ(client: AsyncClient):
    """name 3 点 > description 2 点 > 本文 1 点（ADR-006）."""
    # 更新日時の降順とは逆の順で登録し、日時順の結果と区別できるようにする
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("name-hit", "説明", body="本文")),
    )
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("desc", "name-hit を含む説明", body="本文")),
    )
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("body", "説明", body="name-hit を含む本文")),
    )

    ranked = [s["name"] for s in (await client.get("/skills", params={"q": "name-hit"})).json()]
    assert ranked == ["name-hit", "desc", "body"]


async def test_関連度が同点なら更新日時の降順(client: AsyncClient):
    await upload(client, make_skill_zip(skill_md=build_skill_md("tie-old", "説明")))
    await upload(client, make_skill_zip(skill_md=build_skill_md("tie-new", "説明")))

    ranked = [s["name"] for s in (await client.get("/skills", params={"q": "tie"})).json()]
    assert ranked == ["tie-new", "tie-old"]


async def test_複数タグはANDで絞り込む(client: AsyncClient):
    await upload(
        client,
        make_skill_zip(skill_md=build_skill_md("both", "説明", ["slack", "notification"])),
    )
    await upload(client, make_skill_zip(skill_md=build_skill_md("one", "説明", ["slack"])))

    # 繰り返しパラメータ ?tag=slack&tag=notification
    filtered = await client.get("/skills", params=[("tag", "slack"), ("tag", "notification")])
    assert [s["name"] for s in filtered.json()] == ["both"]
    # 1 つだけなら両方出る
    assert len((await client.get("/skills", params={"tag": "slack"})).json()) == 2


async def test_詳細はSKILL_mdの本文を返す(client: AsyncClient):
    body = "# 使い方\n\nここに手順を書く。"
    response = await upload(
        client, make_skill_zip(skill_md=build_skill_md("with-body", "説明", body=body))
    )
    detail = (await client.get(f"/skills/{response.json()['id']}")).json()
    assert detail["skill_md_body"] == body
    # frontmatter は含まない（name / description は構造化して別に持っている）
    assert "---" not in detail["skill_md_body"]


async def test_frontmatterのnameは本文ヒットにならない(client: AsyncClient):
    """本文に frontmatter を含めると、name ヒットが常に本文ヒットも兼ねてしまう."""
    await upload(client, make_skill_zip(skill_md=build_skill_md("uniquename", "説明", body="本文")))
    found = (await client.get("/skills", params={"q": "uniquename"})).json()
    assert found[0]["matched_fields"] == ["name"]
    assert found[0]["snippet"] is None


async def test_一覧は最新版の更新日時の降順(client: AsyncClient):
    await upload(client, make_skill_zip(skill_md=build_skill_md("first", "1 番目")))
    await upload(client, make_skill_zip(skill_md=build_skill_md("second", "2 番目")))
    # first に新しい版を足すと、first が先頭に来る
    await upload(client, make_skill_zip(skill_md=build_skill_md("first", "1 番目 v2")))

    names = [s["name"] for s in (await client.get("/skills")).json()]
    assert names == ["first", "second"]


# ---------------------------------------------------------------------------
# 異常系: 検証エラーが正しいステータスと日本語メッセージで返る
# ---------------------------------------------------------------------------


async def test_ZIPでないファイルは400(client: AsyncClient):
    response = await upload(client, b"not a zip")
    assert response.status_code == 400
    assert "ZIP" in response.json()["detail"]


async def test_path_traversalを含むZIPは400(client: AsyncClient):
    data = make_zip_with_raw_entries({"SKILL.md": DEFAULT_SKILL_MD, "../../etc/evil": "payload"})
    response = await upload(client, data)
    assert response.status_code == 400
    assert "安全でないパス" in response.json()["detail"]


async def test_symlinkを含むZIPは400(client: AsyncClient):
    data = make_zip_with_raw_entries(
        {"SKILL.md": DEFAULT_SKILL_MD}, symlinks={"secret": "/etc/shadow"}
    )
    response = await upload(client, data)
    assert response.status_code == 400
    assert "シンボリックリンク" in response.json()["detail"]


async def test_サイズ超過のZIPは413(client: AsyncClient):
    # 展開後 60MB（既定上限 50MB 超）。圧縮後は数十 KB なので転送は軽い
    response = await upload(client, make_zip_bomb(60 * 1024 * 1024))
    assert response.status_code == 413
    assert "合計サイズ" in response.json()["detail"]


async def test_SKILL_mdがないZIPは422(client: AsyncClient):
    response = await upload(client, make_zip({"README.md": "hello"}))
    assert response.status_code == 422
    assert "SKILL.md" in response.json()["detail"]


async def test_frontmatterが不正なZIPは422(client: AsyncClient):
    response = await upload(client, make_skill_zip(skill_md="# frontmatter がない"))
    assert response.status_code == 422
    assert "frontmatter" in response.json()["detail"]


async def test_空のファイルは400(client: AsyncClient):
    response = await upload(client, b"")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# 404 と health
# ---------------------------------------------------------------------------


async def test_存在しないIDは404(client: AsyncClient):
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/skills/{missing}")).status_code == 404
    assert (await client.get(f"/skills/{missing}/download")).status_code == 404


async def test_存在しない版は404(client: AsyncClient):
    response = await upload(client, make_skill_zip())
    skill_id = response.json()["id"]
    missing = await client.get(f"/skills/{skill_id}/download", params={"version": 99})
    assert missing.status_code == 404
    assert "版" in missing.json()["detail"]


async def test_不正なUUIDは422(client: AsyncClient):
    """FastAPI のパスパラメータ検証に任せている部分."""
    assert (await client.get("/skills/not-a-uuid")).status_code == 422


async def test_healthはDB接続込みで200(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
