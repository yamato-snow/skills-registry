/**
 * ヒット語のハイライト（ADR-006）。
 *
 * **`dangerouslySetInnerHTML` を使わない**のがこのファイルの要点。
 * 「`<mark>` タグを文字列として埋め込む」実装にすると、検索語も本文も
 * ユーザー入力である以上、そこが XSS の経路になる。テキストを分割して
 * React 要素として組み立てれば、React が自動でエスケープするので
 * **危険な経路がそもそも存在しない**（ADR-007 の Markdown 描画と同じ考え方）。
 */

import type { ReactNode } from "react";

/** 正規表現のメタ文字を無効化する。検索語に `.` や `*` が入っても文字通り扱う。 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * `text` の中の `tokens` を `<mark>` で包んだ React ノードを返す。
 *
 * 大文字小文字を区別しないのは、サーバ側の `ILIKE` と一致させるため。
 */
export function highlight(text: string, tokens: string[]): ReactNode {
  const valid = tokens.filter(Boolean);
  if (!text || valid.length === 0) return text;

  const pattern = new RegExp(`(${valid.map(escapeRegExp).join("|")})`, "gi");
  // キャプチャグループ付きの split は「非マッチ, マッチ, 非マッチ, ...」と
  // 交互に並ぶ。奇数番目がヒット語になる
  return text.split(pattern).map((part, index) =>
    index % 2 === 1 ? (
      <mark key={index} className="rounded bg-amber-200 px-0.5 text-slate-900">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}
