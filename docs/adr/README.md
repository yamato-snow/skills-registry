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
| [002](ADR-002-zip-security-in-memory-inspection.md) | ZIP セキュリティ検証 | ディスクに展開せず in-memory で検査し、展開起因の攻撃面をゼロにする。*Amended by 008* |
| [003](ADR-003-storage-abstraction.md) | ストレージ抽象化 | `StorageBackend` Protocol + `LocalStorage`。S3 移行の変更範囲を閉じる |
| [004](ADR-004-search-postgres-ilike.md) | 検索方式 | PostgreSQL の `ILIKE` 部分一致。拡張パス（pg_trgm → 全文 → ベクトル）を明記。*Amended by 006* |
| [005](ADR-005-frontend-data-fetching.md) | フロントのデータ取得 | 読み取りは Server Components、途中状態が要る箇所だけ Client Component |
| [006](ADR-006-search-multi-token-relevance-snippet.md) | 検索の当たり方 | 複数語 AND・関連度順・スニペット。`ILIKE` は維持し pg_trgm は入れない |
| [007](ADR-007-store-skill-md-body.md) | `SKILL.md` 本文の保存 | 本文を DB に持ち、検索対象と詳細プレビューの両方に使う |
| [008](ADR-008-validation-limits-and-utf8.md) | 入力検証の上限値と UTF-8 | 各上限が何を守るかを再導出。`MAX_FILES` を 2000 へ、他は実測で維持。*Amends 002* |

## Status の作法（Superseded と Amended の使い分け）

ADR は追記していく記録なので、**古い ADR を書き換えるのではなく、新しい ADR との関係をヘッダに記す**。

| 新しい ADR が何をしたか | 旧 ADR の Status | 旧 ADR に足すヘッダ | 新 ADR に足すヘッダ |
|---|---|---|---|
| **Decision を覆した** | `Superseded` に変える | `Superseded by ADR-00X` | `Supersedes ADR-00Y` |
| **Decision の範囲を広げただけ**（結論は生きている） | `Accepted` のまま | `Amended by ADR-00X` | `Amends ADR-00Y` |

判定は「**旧 ADR の Decision を今読んで、そのとおりに実装されているか**」で決める。ADR-004 の Decision は「`ILIKE` による部分一致を採用する」で、ADR-006 のあともそのとおりに実装されている（変わったのは当たり方の質だけ）。だから ADR-004 は `Accepted` のまま `Amended by` が付いている。

## 判断の通底する方針

001 / 003 / 004 / 006 が同じ考え方で書かれている。

- **今ある問題だけを解く** — 非同期化も GIN インデックスも、効果が出る規模にまだ達していない。ADR-006 で pg_trgm を見送ったのも、ADR-004 の「効果が出ない最適化を先に入れない」をそのまま適用した結果
- **ただし、逃げ道の見積もりは先に立てておく** — 「いつ・何を・どこまで変えれば移行できるか」を Decision と拡張パスに書く
- **安全性は検知ではなく構造で担保する**（002 / 007）— 攻撃を弾くより、攻撃が成立する経路を作らない。ZIP を展開しないことと、生 HTML をパースしないことは同じ判断の別の適用先
