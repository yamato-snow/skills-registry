# ADR（Architecture Decision Records）

このプロジェクトで固定した設計判断の記録。**結論よりも「なぜ他の案を採らなかったか」に重心を置いて書いている。**

各 ADR のフォーマット:

- **Status / Date** — 現在の状態と決定日
- **Context** — その判断が必要になった背景・前提・規模感
- **Options Considered** — 検討した案。各案に Pros / Cons と「複雑さ・コスト・習熟度」の評価
- **Decision** — 採用案と決め手
- **Consequences** — この決定が後続に及ぼす制約・作業

| # | タイトル | 決定 |
|---|---|---|
| [001](ADR-001-zip-parsing-sync-vs-async.md) | ZIP 解析方式 | リクエスト内で同期処理する（ワーカー分離しない）。移行基準を明記 |
| [002](ADR-002-zip-security-in-memory-inspection.md) | ZIP セキュリティ検証 | ディスクに展開せず in-memory で検査し、展開起因の攻撃面をゼロにする |
| [003](ADR-003-storage-abstraction.md) | ストレージ抽象化 | `StorageBackend` Protocol + `LocalStorage`。S3 移行の変更範囲を閉じる |
| [004](ADR-004-search-postgres-ilike.md) | 検索方式 | PostgreSQL の `ILIKE` 部分一致。拡張パス（pg_trgm → 全文 → ベクトル）を明記 |
| [005](ADR-005-frontend-data-fetching.md) | フロントのデータ取得 | 読み取りは Server Components、途中状態が要る箇所だけ Client Component |

## 判断の通底する方針

3 本の ADR（001 / 003 / 004）が同じ考え方で書かれている。

- **今ある問題だけを解く** — 非同期化も GIN インデックスも、効果が出る規模にまだ達していない
- **ただし、逃げ道の見積もりは先に立てておく** — 「いつ・何を・どこまで変えれば移行できるか」を Decision と拡張パスに書く
- **安全性は検知ではなく構造で担保する**（002）— 攻撃を弾くより、攻撃が成立する経路を作らない
