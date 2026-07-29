# 手動テスト手順書

画面から**正常系と異常系を一通り確かめる**ための手順書。自動テスト（pytest）が
何を守っているかとは別に、「実際に触ったときにそう振る舞うか」を人の目で見る。

判定欄は空けてある。実施しながら ✅ / ❌ を書き込む。

| | |
|---|---|
| 実施日 | |
| 実施者 | |
| 対象コミット | |
| 備考（❌ があれば概要） | |

> **直近の実施記録**: 2026-07-29 / 実装セッション（自動操作） / `253503f`。
> **35 項目すべて ✅**（結果は [`_results/2026-07-29.md`](_results/2026-07-29.md)）。
> ただし目視で判断すべき項目（後述の「人が見るべきもの」）は自動では代替できないので、
> 改めて人の目で確認すること。

> ❌ が出た行は、**そのまま次へ進まずに記録を残す**。何が起きたか（画面の表示・
> エラーメッセージ・スクリーンショット）を備考欄か別途メモに書いてから進む。
> 「あとで思い出す」は再現しない。

---

## §1 準備

**フェーズ 2 でスキーマが変わっている**（`SKILL.md` 本文を保存するカラムが増えた。
[ADR-007](adr/ADR-007-store-skill-md-body.md)）。マイグレーションは起動時の
`create_all` 任せなので、**既存の DB には反映されない**。必ず `-v` を付けて
volume ごと作り直す。

**1. 起動する（DB を作り直す）**

```bash
docker compose down -v && docker compose up -d --build
```

**2. 手動テスト用の ZIP を 16 パターン生成する**

```bash
cd backend && python3 scripts/make_test_zips.py
```

> 2 つのスクリプトは**標準ライブラリだけで動く**ので、仮想環境も依存のインストールも要らない。
> Python 3 が入っていればそのまま実行できる（`uv run python scripts/...` でも同じ）。

`manual-test/zips/` に §2 の No と同じ番号のファイル名で出力される。このディレクトリは
`.gitignore` 済みで、リポジトリには入らない（危険なエントリを含む ZIP を配布しない方針。
[ADR-002](adr/ADR-002-zip-security-in-memory-inspection.md)）。

> **06 / 07 / 08 は意図的に危険な ZIP。手元で展開しないこと。** 画面へアップロードして
> 拒否されることを確かめるためのもの。

**3. 検索試験用のデータを投入する**

```bash
cd backend && python3 scripts/seed_search_data.py
```

8 件が `201` で返れば成功。**この投入自体がアップロード経路の確認を兼ねている**ので、
ここで失敗したら §2 以降には進まず原因を先に潰す。

**4. 画面を開く**

http://localhost:3000

### ポートを変える場合の注意

8000 / 3000 が他のプロジェクトに取られている場合はポートをずらす。**そのとき、
`BACKEND_PORT` は毎回のコマンドに付ける**（`--build` を含むものにも）。

```bash
BACKEND_PORT=8010 FRONTEND_PORT=3010 docker compose up -d --build
```

```bash
cd backend && python3 scripts/seed_search_data.py http://localhost:8010
```

ブラウザ用の API URL（`NEXT_PUBLIC_API_URL`）は**ビルド時にフロントのバンドルへ
焼き込まれる**（[ADR-005](adr/ADR-005-frontend-data-fetching.md) / [learnings.md #9](learnings.md)）。
`BACKEND_PORT` を付けずに一度でも `--build` すると、**画面は 8000 番を見に行くイメージのまま
固定される**。症状はアップロードだけが失敗することで、一覧や詳細（Server Component から
コンテナ内で取得）は正常に見えるため気づきにくい。

焼き込まれている URL はこれで確認できる。

```bash
docker compose exec frontend sh -c 'grep -rho "http://localhost:[0-9]*" .next/static | sort -u'
```

食い違っていたら、`BACKEND_PORT` を付けて作り直す。

```bash
BACKEND_PORT=8010 FRONTEND_PORT=3010 docker compose up -d --build frontend
```

---

## §2 アップロード試験（16 件）

すべて画面の「アップロード」からファイルを選んで実行する。**エラーはすべて日本語**で
表示されること（英語のスタックトレースや `Internal Server Error` が出たら ❌）。

`manual-test/zips/` の中のファイルを、**01 から順に**実行する（04 は 01 の結果に依存する）。

| No | 目的 | 使用 ZIP | 手順 | 期待結果 | 判定 |
|---|---|---|---|---|---|
| 01 | ルート直下の SKILL.md を登録できる | `01_normal_root.zip` | アップロード | 成功。一覧に `mt-normal` が `v1` で出る。タグ `#sample` が付く | |
| 02 | 1 階層下の SKILL.md も登録できる | `02_normal_nested.zip` | アップロード | 成功。一覧に `mt-nested` が出る | |
| 03 | tags が無くても登録できる | `03_no_tags.zip` | アップロード | 成功。`mt-no-tags` が出る。**タグは 1 つも表示されない** | |
| 04 | 同名の再アップロードが新しい版になる | `04_reupload.zip` | アップロード → 一覧 → `mt-normal` の詳細 | 成功。**Skill は増えず** `mt-normal` が `v2` になる。説明が「01 の説明を書き換えた版」に変わり、版履歴に v2 と v1 が並ぶ | |
| 05 | ZIP でないファイルを拒否する | `05_not_a_zip.zip` | アップロード | 失敗。「ZIP ファイルとして読み取れません」 | |
| 06 | path traversal を拒否する | `06_path_traversal.zip` | アップロード | 失敗。「安全でないパスを含む ZIP です: `'../../evil.sh'`」 | |
| 07 | シンボリックリンクを拒否する | `07_symlink.zip` | アップロード | 失敗。「シンボリックリンクを含む ZIP は受け付けません」 | |
| 08 | バックスラッシュのパスを拒否する | `08_backslash.zip` | アップロード | 失敗。「安全でないパスを含む ZIP です」 | |
| 09 | ファイル数の上限を守る | `09_too_many_files.zip` | アップロード | 失敗。「ZIP 内のファイル数が上限（500 件）を超えています」 | |
| 10 | zip bomb を**解凍せずに**弾く | `10_zip_bomb.zip` | アップロード | 失敗。「展開後の合計サイズが上限（50MB）を超えています」。**体感で一瞬**（数十 KB のファイルを送っただけで、60MB を展開していない証拠。待たされたら ❌） | |
| 11 | SKILL.md が無い ZIP を拒否する | `11_no_skill_md.zip` | アップロード | 失敗。「SKILL.md が見つかりません。…」 | |
| 12 | SKILL.md が複数ある ZIP を拒否する | `12_multiple_skill_md.zip` | アップロード | 失敗。「SKILL.md が複数見つかりました（SKILL.md、sub/SKILL.md）。1 つにしてください」 | |
| 13 | frontmatter の必須項目を検査する | `13_bad_frontmatter.zip` | アップロード | 失敗。「SKILL.md の frontmatter に name がありません」 | |
| 14 | UTF-8 でない SKILL.md を拒否する | `14_not_utf8.zip` | アップロード | 失敗。「SKILL.md を UTF-8 として読み取れません」 | |
| 15 | SKILL.md 単体の上限を守る | `15_huge_skill_md.zip` | アップロード | 失敗。「SKILL.md が大きすぎます（1024KB 以内）」 | |
| 16 | macOS の付随ファイルを表示から除く | `16_macosx_junk.zip` | アップロード → `mt-macosx` の詳細 | 成功。ファイル構成に **`__MACOSX/` と `.DS_Store` が出ない**（`SKILL.md` だけが並ぶ）。※ 表示から除くだけで、**サイズと件数の集計には含めている**（除外すると、そこに zip bomb を仕込まれて上限チェックをすり抜けるため） | |

### §2 の後始末

§2 で登録された 4 件（`mt-normal` v2 / `mt-nested` / `mt-no-tags` / `mt-macosx`）は
そのまま残してよい。§3 の検索語はどれもこの 4 件に当たらないよう選んである。

---

## §3 検索試験

§1 の 3 で投入した 8 件に対して実行する。

**§2 を実施済みだと、そこで登録された `mt-` で始まる 4 件（`mt-normal` / `mt-nested` /
`mt-no-tags` / `mt-macosx`）が一覧に混ざる。** ただし §3 の検索語はどれも `mt-` 系に
当たらないので、**No.18 以降の件数・順序は変わらない**。影響を受けるのは、条件なしで
全件を見る No.17 だけ。

検索欄は一覧ページの右上。タグは各カードの `#タグ` を押す。

| No | 目的 | 手順 | 期待結果 | 判定 |
|---|---|---|---|---|
| 17 | 全件が更新日時の降順で出る | 検索欄を空にして「条件をクリア」 | §2 未実施なら **8 件**、実施済みなら先頭に `mt-macosx` / `mt-normal` / `mt-no-tags` / `mt-nested` が加わって **12 件**。seed の 8 件は上から `xss-check` / `slack-notifier` / `slack-uploader` / `teams-notifier` / `report_builder` / `reportXbuilder` / `csv-cleaner` / `mail-digest`（＝投入と逆順）。「ヒット:」の表示は出ない | |
| 18 | 関連度順（名前 > 説明 > 本文） | `slack` で検索 | **3 件**。上から `slack-notifier`（ヒット: 名前・説明）/ `slack-uploader`（ヒット: 名前・説明）/ `mail-digest`（ヒット: **本文**）。**本文だけに当たったものが最下位**。件数の下に「関連度順」と出る | |
| 19 | 本文ヒットにスニペットが出る | 18 の結果のまま `mail-digest` のカードを見る | 説明の下に抜粋「# 概要 要約結果は **Slack** にも投げられる。…」が出て、`Slack` に色が付く。**なぜこれが出たのかがその場で分かる**こと | |
| 20 | ヒット語がハイライトされる | 18 の結果を見る | 名前・説明・抜粋の中の `slack` / `Slack` が黄色く光る。**大文字小文字が違っても光る** | |
| 21 | 日本語の部分一致が効く | `通知` で検索 | **2 件**。`slack-notifier`（説明が「**Slack通知**を任意のチャンネルへ送る」）/ `teams-notifier`。**単語の途中でも当たる**（`Slack通知` の中の `通知`）ことが要点 | |
| 22 | 複数語が AND で絞れる | `slack 通知` で検索（半角空白） | **1 件**、`slack-notifier` のみ。`slack-uploader` は「通知」を持たないので落ち、`teams-notifier` は「slack」を持たないので落ちる。**語を足すほど絞れる** | |
| 23 | 全角空白でも同じ結果になる | `slack　通知` で検索（**全角**空白） | 22 と**まったく同じ 1 件**。日本語入力のまま打っても同じに効く | |
| 24 | 語を足して 0 件になる | `slack 存在しない語` で検索 | **0 件**。「条件に一致する Skills がありません」と、「語を減らすと広がります」の案内が出る | |
| 25 | 本文だけの語でも探せる | `webhook` で検索 | **1 件**、`slack-notifier`（ヒット: **本文**）。抜粋「# 使い方 **Webhook** URL を環境変数に設定して実行する。」。**説明に書いていない語で見つかる**のがこの機能の主目的 | |
| 26 | `_` がワイルドカードにならない | `report_builder` で検索 | **1 件**、`report_builder` のみ。**`reportXbuilder` が出たら ❌**（`_` が「任意の 1 文字」として解釈されている） | |
| 27 | `%` で全件マッチにならない | `%` だけを入れて検索 | **0 件**。8 件全部出たら ❌ | |
| 28 | タグで絞り込める | 「条件をクリア」→ `slack-notifier` の `#notification` を押す | **2 件**（`slack-notifier` / `teams-notifier`）。上部に「タグで絞り込み中」と `#notification ✕` が出る。URL が `/?tag=notification` になる | |
| 29 | タグを足すと AND で絞れる | 28 の状態で `slack-notifier` の `#slack` を押す | **1 件**、`slack-notifier` のみ。上部に `#notification ✕` と `#slack ✕` が並ぶ。URL が `/?tag=notification&tag=slack` になる | |
| 30 | タグを外せる | 29 の状態で上部の `#slack ✕` を押す | 28 の状態（2 件）に戻る | |
| 31 | 検索語とタグを併用できる | 「条件をクリア」→ `slack` で検索 → `#notification` を押す | **1 件**、`slack-notifier`。検索欄に `slack` が残ったままタグが効く | |
| 32 | 条件が URL で共有できる | 29 の URL をコピーして新しいタブに貼る | 同じ絞り込み結果が出る。**ログインも操作の再現も要らない** | |
| 33 | SKILL.md が画面で読める | 「条件をクリア」→ `slack-notifier` の詳細を開く | 「SKILL.md」の見出しの下に本文が表示される。`# 使い方` が**見出しの大きさ**で描画される（すべて同じ大きさの平文なら ❌）。frontmatter（`---` や `name:`）は表示されない | |
| 34 | **本文の HTML が実行されない（XSS）** | `xss-check` の詳細を開く | 本文に `<script>alert(1)</script>` が**そのまま文字として**表示される。**アラートが出たら ❌。その行が消えていても ❌**（＝HTML として解釈されている）。ページ内の「上の行がタグごと文字として見えていれば正しい」という一文も表示される | |
| 35 | ダウンロードできる | `slack-notifier` の詳細で「最新版 (v1) をダウンロード」 | `slack-notifier-v1.zip` が落ちてくる。展開すると `slack-notifier/SKILL.md` がある | |

### 人が見るべきもの（自動操作では代替できない）

上の 35 項目は機械的に判定できるが、次の 4 つは**体感と目視でしか判定できない**。

| | 見るところ |
|---|---|
| ドラッグ＆ドロップ | 枠にファイルを重ねたときに枠線が変わるか。落として正しく選択されるか |
| ファイル選択ダイアログ | 枠をクリックしてダイアログが開き、ZIP を選べるか |
| ダウンロード | ブラウザが実際にファイルを保存し、Finder で展開できるか（No.35） |
| 見た目 | 一覧・詳細のレイアウトが崩れていないか。ハイライトの色が読みづらくないか |

### 判定の目安

- **17〜27 のどれかが ❌** → 検索の絞り込み・順位のロジック（`backend/app/services/search.py` と
  `skill_service.list_skills`）。[ADR-006](adr/ADR-006-search-multi-token-relevance-snippet.md) の
  「Decision」の 3 項目と突き合わせる
- **28〜32 が ❌** → タグの URL 組み立て（`frontend/lib/search.ts`）
- **33〜34 が ❌** → 本文の保存・描画（[ADR-007](adr/ADR-007-store-skill-md-body.md)）。
  とくに **34 は最優先**。`rehype-raw` が入っていないか、`dangerouslySetInnerHTML` が
  使われていないかを真っ先に見る
