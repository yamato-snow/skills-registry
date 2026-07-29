"use client";

/**
 * なぜ Client Component なのか（ADR-005）:
 * 入力中の文字列という「ユーザー操作の途中状態」を持つ必要があるため。
 * これがこのプロジェクトで Client を選ぶ唯一の基準で、他は Server にする。
 *
 * ただし検索結果そのものはここで持たない。GET のフォーム送信で
 * searchParams を変え、サーバ側で取り直す。クライアントに結果配列を
 * 抱えないので、状態の二重管理が起きない（URL がそのまま共有できる副産物付き）。
 */

import Link from "next/link";
import { useState } from "react";

type Props = {
  defaultQuery: string;
  tags: string[];
};

export function SearchForm({ defaultQuery, tags }: Props) {
  const [query, setQuery] = useState(defaultQuery);

  return (
    <form method="GET" action="/" className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        name="q"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="名前・説明・本文で検索（空白区切りで絞り込み）"
        aria-label="検索キーワード"
        className="w-80 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
      />
      {/*
        タグ絞り込みはリンクから来るので、検索時も維持されるよう hidden で持ち回る。
        同じ name の input を並べると、GET のフォーム送信でも
        ?tag=a&tag=b という繰り返しパラメータになる（リンク側と同じ形）
      */}
      {tags.map((tag) => (
        <input key={tag} type="hidden" name="tag" value={tag} />
      ))}
      <button
        type="submit"
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        検索
      </button>
      {(defaultQuery || tags.length > 0) && (
        <Link href="/" className="text-sm text-slate-500 underline hover:text-slate-800">
          条件をクリア
        </Link>
      )}
    </form>
  );
}
