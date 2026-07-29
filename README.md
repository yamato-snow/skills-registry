# Skills Registry

Skills パッケージ（`SKILL.md` を含む ZIP）を **登録・検索・配布** する社内向けレジストリ。

このリポジトリの目的は「**Skills レジストリを作るときに何をどう決めるべきか**」を、動くもので検証すること。ZIP という危険な入力を受け取るシステムのセキュリティ設計、将来のクラウド移行を見据えた抽象化の引き方、App Router のサーバ／クライアント境界——これらを実際に手を動かして確かめ、判断の過程を [ADR](docs/adr/README.md) として残している。

**成果物はコードだけではなく、判断の記録も含む。** 迷ったところは [docs/learnings.md](docs/learnings.md) に率直に書いてある。

![一覧画面](docs/images/list.png)

<details>
<summary>詳細画面・アップロード画面</summary>

![詳細画面](docs/images/detail.png)
![アップロード画面](docs/images/upload.png)

</details>

---

## 5 分で動かす

必要なもの: **Docker** だけ（Python / Node.js のローカルインストールは不要）。

```bash
docker compose up --build
```

- 画面: http://localhost:3000
- API ドキュメント（Swagger UI）: http://localhost:8000/docs

ポートが他のプロジェクトと衝突する場合は、ホスト側だけ変更できる。

```bash
BACKEND_PORT=8010 FRONTEND_PORT=3010 docker compose up --build
```

### 試してみる

1. 「アップロード」から ZIP をドラッグ＆ドロップする。手元に無ければ、以下で作れる。

```bash
mkdir -p /tmp/my-skill && cat > /tmp/my-skill/SKILL.md <<'EOF'
---
name: my-first-skill
description: 動作確認用のサンプル
tags: [sample]
---

# 使い方
EOF
(cd /tmp && zip -r my-skill.zip my-skill)
```

2. 一覧で検索し、詳細で `SKILL.md` の中身・ファイル構成・版履歴を確認する
3. 同じ名前のまま `SKILL.md` を書き換えて再アップロードすると、**新しい版**として追加される
4. 危険な ZIP（`../` を含むもの等）を投げると、日本語のエラーで拒否される

> **既にフェーズ 1 を動かしていた場合は、先に `docker compose down -v` が必要。**
> `SKILL.md` 本文を保存するカラムが増えており（[ADR-007](docs/adr/ADR-007-store-skill-md-body.md)）、マイグレーションは起動時の `create_all` 任せなので既存の DB には反映されない。

### 検索の使い方

- **空白区切りで語を足すほど絞れる**（AND）。全角空白でも同じ（`slack 通知` / `slack　通知`）
- 検索対象は **名前・説明・`SKILL.md` 本文**の 3 つ。当たった場所は各カードに「ヒット: 名前・本文」と出る。本文に当たった場合はその周辺が抜粋で表示される
- `q` を指定すると**関連度順**（名前 > 説明 > 本文）に並ぶ。指定しなければ更新日時の降順
- **タグは複数選べる**（AND）。タグを押すと絞り込みに足され、もう一度押すと外れる。条件はそのまま URL に出るので、共有もブックマークもできる

判断の理由は [ADR-006](docs/adr/ADR-006-search-multi-token-relevance-snippet.md) にある。

### 止める

```bash
docker compose down
```

DB とアップロード済みファイルごと消す場合は `docker compose down -v` と `rm -rf ./storage`。

---

## Skills パッケージの形式

ZIP のルート直下、または **1 階層下のディレクトリ直下** に `SKILL.md` を 1 つ置く。

```
my-skill.zip
└── my-skill/
    ├── SKILL.md      ← ここか、ZIP のルート直下
    └── scripts/
        └── run.sh
```

`SKILL.md` の先頭に YAML frontmatter を書く。`name` と `description` が必須、`tags` は任意。

```markdown
---
name: slack-notifier
description: Slack の任意チャンネルへ通知を送る
tags: [slack, notification]
---
```

同じ `name` で再アップロードすると、新しい Skill ではなく**新しい版**になる。

---

## 設計

判断の記録が主たるドキュメント。結論よりも「なぜ他の案を採らなかったか」に重心を置いている。

| ドキュメント | 内容 |
|---|---|
| [docs/design.md](docs/design.md) | 全体像（構成図・ER 図・API 仕様・ディレクトリ構成）を 1 ページに |
| [docs/adr/](docs/adr/README.md) | 設計判断 7 本。各案の Pros / Cons と、**いつこの判断を見直すか** |
| [docs/learnings.md](docs/learnings.md) | 実装中に詰まった点と、迷って決めきれなかったこと |
| [docs/manual-test.md](docs/manual-test.md) | 手動テスト手順書（アップロード 16 件 + 検索 19 件・判定欄つき） |
| [docs/tasks.md](docs/tasks.md) | 実装のタスク分解 |

とくに次の 3 つが中核。

- **[ADR-002](docs/adr/ADR-002-zip-security-in-memory-inspection.md): ZIP をディスクに展開しない** — `extract` / `extractall` を一度も呼ばない。ファイルシステムへ書き込む処理が存在しなければ、path traversal も symlink 攻撃も成立する先がない。攻撃を検知するのではなく、攻撃が成立する経路を作らない
- **[ADR-001](docs/adr/ADR-001-zip-parsing-sync-vs-async.md): 同期処理を選ぶ** — 非同期ワーカーが解決する問題を、この規模ではまだ抱えていない。ただし「いつ非同期化すべきか」の基準は 3 つ明記してある
- **[ADR-006](docs/adr/ADR-006-search-multi-token-relevance-snippet.md): 検索は速くせず、当たり方を直す** — 3 件しかないシステムで pg_trgm を入れても得るものがない。実際に効いていなかったのは複数語・順位・本文の 3 点で、そこだけを `ILIKE` のまま直した

### 構成

| | |
|---|---|
| Backend | Python 3.12 / FastAPI / SQLAlchemy 2.0 (async) / Pydantic v2 / PostgreSQL 16 |
| Frontend | Next.js 15 (App Router) / TypeScript / Tailwind CSS |
| インフラ | Docker（マルチステージ）/ docker compose |
| CI | GitHub Actions（ruff / pytest+カバレッジ / ESLint / Prettier / next build） |

**このレジストリは Skills を実行しない。** 保管と配布のみを行う。これはセキュリティ境界であり、恒久的に対象外とする。

---

## 開発

### backend

```bash
cd backend
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
```

テストは **実 PostgreSQL** に対して回す（JSONB・`DISTINCT ON`・`ILIKE` は PostgreSQL 固有で、SQLite で緑にしても本番の保証にならないため）。DB だけ起動しておく。

```bash
docker compose up -d db
```

```bash
cd backend && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/skills_registry_test .venv/bin/pytest --cov
```

`DATABASE_URL` を明示するのは 2 つの理由から。**ホスト側のポートが 55432 にずれている**こと（compose の `db` は `55432:5432`。他プロジェクトの PostgreSQL と衝突しないようにするため）と、**開発中のデータを消さないよう別の DB 名（`skills_registry_test`）を使う**こと。この DB は無ければ自動で作られる。

DB へ接続できない場合、API テストはスキップされ、`zip_inspector` と `search` の単体テストだけが走る。

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

### frontend

```bash
cd frontend && npm ci
npm run dev          # http://localhost:3000
npm run lint && npm run format:check && npm run build
```

`INTERNAL_API_URL`（サーバ用）と `NEXT_PUBLIC_API_URL`（ブラウザ用）で API の URL が分かれている。理由は [ADR-005](docs/adr/ADR-005-frontend-data-fetching.md) を参照。

### 環境変数

すべて [docs/design.md §7](docs/design.md) に一覧がある。compose を使う場合は設定済み。

### 手動テスト

自動テストが守っているものとは別に、**画面から正常系・異常系を一通り確かめる**ための
手順書がある: [docs/manual-test.md](docs/manual-test.md)（アップロード 16 件 + 検索 19 件、判定欄つき）。

試験用の ZIP はリポジトリに同梱せず、その場で生成する。危険なエントリ（path traversal・
symlink）を含む ZIP をクローンした人の手元に置かないため（[ADR-002](docs/adr/ADR-002-zip-security-in-memory-inspection.md) の帰結）。

```bash
docker compose down -v && docker compose up -d --build
```

```bash
cd backend && python3 scripts/make_test_zips.py && python3 scripts/seed_search_data.py
```

`make_test_zips.py` は 16 パターンを `manual-test/zips/`（gitignored）へ出力し、
`seed_search_data.py` は検索確認用の 8 件を **API 経由で**投入する（投入自体がアップロード
経路の回帰確認を兼ねる）。どちらも**標準ライブラリだけで動く**ので、仮想環境も依存の
インストールも要らない。

---

## 既知の制約

プロトタイプとしての割り切りを明示しておく（[docs/design.md §8](docs/design.md) に詳細）。

- **検索は件数に線形**。数千件を超えたら `pg_trgm` を検討する（アプリのクエリ変更は不要）
- **マイグレーションは起動時 `create_all`**。スキーマを変えたら `docker compose down -v` で volume を作り直す必要がある。Alembic はデータを消せなくなった時点で導入する
- **ローカルストレージは ECS ではエフェメラル**。本番化には `S3Storage` の実装が必須（差し替えは DI 1 行）
- **認証・認可は未実装**。ロールの設計と嵌め込み位置だけ [design.md §6](docs/design.md) に残してある
