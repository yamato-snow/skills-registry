# 実装タスク分解

[design.md](design.md) を実装に落とすための作業リスト。**1 タスク = 1 コミット**を目安にし、コミットメッセージには「何をしたか」ではなく「なぜそうしたか」を書く。

順序は依存関係で決めている。**ZIP インスペクタ（T4）を API より先に作る**のは、そこがこのシステムの中核であり、HTTP の文脈なしに単体で完成させられるため。

## Backend

- [ ] **T1 プロジェクト雛形** — `pyproject.toml`（依存 / ruff / pytest / coverage 設定）、`app/` パッケージ配置
- [ ] **T2 設定** — `core/config.py`（pydantic-settings）。環境変数をここに集約し、コード内に既定値を散らさない
- [ ] **T3 DB モデル** — `db/base.py` / `db/models.py`（Skill / SkillVersion / Tag / skill_tags）/ `db/session.py`（async engine + sessionmaker）
- [ ] **T4 ZIP インスペクタ** ★中核 — `services/zip_inspector.py`。FastAPI 非依存の純粋関数群
- [ ] **T5 インスペクタのテスト** — `tests/helpers.py` の `make_skill_zip()` で ZIP を動的生成。必須 4 種（正常 / `SKILL.md` 欠落 / path traversal / サイズ超過）+ symlink / 件数超過 / frontmatter 不正。カバレッジ 90%+
- [ ] **T6 ストレージ層** — `storage/base.py`（Protocol）/ `storage/local.py`（`LocalStorage`）+ テスト
- [ ] **T7 サービス層** — `services/skill_service.py`。版採番・タグ張り替え・保存順序（ストレージ → DB）
- [ ] **T8 スキーマと API** — `schemas/skill.py` / `api/deps.py` / `api/routes/skills.py` / `main.py`（lifespan で `create_all`、CORS、`/health`）
- [ ] **T9 API テスト** — httpx `AsyncClient` + 実 PostgreSQL。5 エンドポイントの正常系と、400 / 413 / 422 の異常系

## Docker

- [ ] **T10 backend Dockerfile** — マルチステージ（builder → slim runtime）、非 root、uvicorn。**「なぜこの書き方か」のコメントを多めに**
- [ ] **T11 frontend Dockerfile** — deps → build → runner。`standalone` 出力のみコピー、非 root
- [ ] **T12 docker-compose.yml** — db（healthcheck + named volume）/ backend（`depends_on: service_healthy`、`./storage` バインド）/ frontend。設定はすべて環境変数注入

## Frontend

- [ ] **T13 雛形** — `create-next-app`（App Router / TS / Tailwind）、`next.config.ts` に `output: "standalone"`
- [ ] **T14 API クライアント** — `lib/api.ts`。サーバ用 / ブラウザ用を関数名レベルで分離
- [ ] **T15 一覧ページ** — `app/page.tsx`（SC）+ `_components/SearchForm.tsx`（CC）。検索は `searchParams` 経由
- [ ] **T16 詳細ページ** — `app/skills/[id]/page.tsx`（SC）。ファイルツリー + 版履歴 + ダウンロード
- [ ] **T17 アップロードページ** — `app/upload/page.tsx`（CC）。D&D + 送信中表示 + 日本語エラー表示

## CI / 仕上げ

- [ ] **T18 GitHub Actions** — `.github/workflows/ci.yml`。backend（ruff check / format check / pytest + カバレッジ閾値）、frontend（ESLint / Prettier / `next build`）。**デプロイジョブは作らない**
- [ ] **T19 README** — 目的、`docker compose up` 一発の手順、スクリーンショット、docs へのリンク
- [ ] **T20 learnings.md** — 実装中に随時追記（最後にまとめて書かない）

## 完了の判定

- `docker compose up` で 3 サービスが起動し、アップロード → 検索 → 詳細 → ダウンロードが一通り動く
- 悪意ある ZIP が pytest で拒否されることを証明できる
- カバレッジ: `zip_inspector` 90% 以上、全体 70% 以上
- PR で CI がグリーン
