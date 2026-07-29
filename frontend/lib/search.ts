/**
 * 検索条件（キーワード・タグ）と URL の相互変換（ADR-006）。
 *
 * ここにあるのは全部 **純粋関数**で、状態を持たない。それが
 * 「タグ選択 UI を Client Component にしない」判断を支えている（ADR-005）:
 * 「このタグを足した URL / 外した URL」はサーバ側で計算できる導出値でしかなく、
 * クリック＝遷移＝サーバ再取得で完結する。**途中状態が存在しないので
 * Client 化する理由がない。**
 */

/** searchParams の `tag` を正規化する（単一指定・複数指定・未指定を吸収）。 */
export function toTagList(tag: string | string[] | undefined): string[] {
  if (!tag) return [];
  const raw = Array.isArray(tag) ? tag : [tag];
  const tags: string[] = [];
  for (const value of raw) {
    // 取り込み時と同じ規則（trim + 小文字）に揃える。URL に大文字で
    // 書かれても同じ絞り込みになるようにするため
    const name = value.trim().toLowerCase();
    if (name && !tags.includes(name)) tags.push(name);
  }
  return tags;
}

/**
 * 検索語を空白で分割する。
 *
 * バックエンドの `search.tokenize()` と**同じ結果**にならなければならない。
 * ずれると「一覧には出るのにハイライトされない」という説明のつかない状態になる。
 * JavaScript の `\s` は全角空白（U+3000）を含むので、Python の `str.split()` と
 * 分割位置が一致する。
 */
export function tokenizeQuery(q: string): string[] {
  const tokens: string[] = [];
  for (const token of q.trim().split(/\s+/)) {
    if (token && !tokens.includes(token)) tokens.push(token);
  }
  return tokens;
}

export type SearchCondition = {
  q: string;
  tags: string[];
};

/** 検索条件を一覧ページの URL にする。条件が空なら `/`。 */
export function searchHref({ q, tags }: SearchCondition): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  // 繰り返しパラメータ（?tag=a&tag=b）。意味は AND
  for (const tag of tags) params.append("tag", tag);
  const query = params.toString();
  return query ? `/?${query}` : "/";
}

/** 現在の条件に対して、そのタグを足した／外した URL を返す。 */
export function toggleTagHref(condition: SearchCondition, tag: string): string {
  const tags = condition.tags.includes(tag)
    ? condition.tags.filter((name) => name !== tag)
    : [...condition.tags, tag];
  return searchHref({ q: condition.q, tags });
}
