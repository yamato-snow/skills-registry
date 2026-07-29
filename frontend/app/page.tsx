/**
 * 一覧ページ。Server Component（ADR-005）。
 *
 * 表示するだけで「操作の途中状態」がないので Server のまま。データ取得は
 * サーバ内の URL で 1 往復で終わり、ローディング状態の実装が要らない。
 *
 * 検索の高度化（複数語 AND・関連度順・ハイライト・複数タグ）で表示は増えたが、
 * **Client Component は 1 つも増えていない**（ADR-006）。タグの追加・解除は
 * 「その条件の URL へのリンク」でしかなく、途中状態を持たないため。
 */

import Link from "next/link";

import { SearchForm } from "@/app/_components/SearchForm";
import { fetchSkillsFromServer, type SkillSummary } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { highlight } from "@/lib/highlight";
import { type SearchCondition, toTagList, tokenizeQuery, toggleTagHref } from "@/lib/search";

type Props = {
  // Next.js 15 では searchParams が Promise で渡る。
  // tag は繰り返しパラメータなので string にも string[] にもなりうる
  searchParams: Promise<{ q?: string; tag?: string | string[] }>;
};

// API の matched_fields をそのまま出すと "body" などの英語が画面に出てしまう
const FIELD_LABELS: Record<string, string> = {
  name: "名前",
  description: "説明",
  body: "本文",
};

export default async function HomePage({ searchParams }: Props) {
  const { q = "", tag } = await searchParams;
  const condition: SearchCondition = { q, tags: toTagList(tag) };
  const skills = await fetchSkillsFromServer({ q, tags: condition.tags });
  const tokens = tokenizeQuery(q);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Skills 一覧</h1>
          <p className="mt-1 text-sm text-slate-600">
            登録済みの Skills パッケージ {skills.length} 件{q && " / 関連度順"}
          </p>
        </div>
        <SearchForm defaultQuery={q} tags={condition.tags} />
      </div>

      {condition.tags.length > 0 && <ActiveTags condition={condition} />}

      {skills.length === 0 ? (
        <EmptyState hasCondition={Boolean(q || condition.tags.length)} />
      ) : (
        <ul className="grid gap-3">
          {skills.map((skill) => (
            <SkillCard key={skill.id} skill={skill} condition={condition} tokens={tokens} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** 絞り込み中のタグ。クリックで外れる（＝そのタグを抜いた URL へのリンク）。 */
function ActiveTags({ condition }: { condition: SearchCondition }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs">
      <span className="text-slate-500">タグで絞り込み中（すべてを含むもの）</span>
      {condition.tags.map((name) => (
        <Link
          key={name}
          href={toggleTagHref(condition, name)}
          className="rounded-full bg-slate-900 px-2 py-0.5 text-white hover:bg-slate-700"
          title="このタグを外す"
        >
          #{name} ✕
        </Link>
      ))}
    </div>
  );
}

function SkillCard({
  skill,
  condition,
  tokens,
}: {
  skill: SkillSummary;
  condition: SearchCondition;
  tokens: string[];
}) {
  return (
    // カード全体をクリック領域にする（stretched link パターン）。
    // カードは枠線がホバーで変わるので「押せそう」に見えるが、リンクが名前の
    // テキストだけだと、そこ以外を押しても何も起きない。見た目が約束している
    // ことと実際の当たり判定を一致させる。
    //
    // カード自体を <Link> で包まないのは、中にタグへのリンクがあるため。
    // <a> の入れ子は HTML として不正で、ブラウザが構造を壊して解釈する。
    // 代わりに名前リンクの ::after を absolute inset-0 でカード全面へ広げ、
    // タグ側を relative + z-10 で上に載せて、両方を生かす。
    <li className="relative rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-400 focus-within:border-slate-500">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            href={`/skills/${skill.id}`}
            className="font-semibold text-slate-900 hover:underline after:absolute after:inset-0 after:content-['']"
          >
            {highlight(skill.name, tokens)}
          </Link>
          <p className="mt-1 text-sm text-slate-600">{highlight(skill.description, tokens)}</p>
          {skill.snippet && (
            // 本文にしか当たっていないヒットは、これが無いと
            // 「なぜ出てきたのか分からない検索結果」になる
            <p className="mt-2 border-l-2 border-slate-200 pl-2 text-xs text-slate-500">
              {highlight(skill.snippet, tokens)}
            </p>
          )}
        </div>
        <span className="shrink-0 rounded bg-slate-100 px-2 py-1 text-xs text-slate-600">
          v{skill.latest_version}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {skill.tags.map((name) => {
          const active = condition.tags.includes(name);
          return (
            <Link
              key={name}
              href={toggleTagHref(condition, name)}
              // z-10 でカード全面のオーバーレイより上に出す。これが無いと
              // タグを押しても詳細ページへ飛んでしまう
              className={`relative z-10 rounded-full px-2 py-0.5 ${
                active
                  ? "bg-slate-900 text-white hover:bg-slate-700"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
              title={active ? "このタグを外す" : "このタグを絞り込みに足す"}
            >
              #{name}
            </Link>
          );
        })}
        {skill.matched_fields.length > 0 && (
          <span className="text-slate-400">
            ヒット: {skill.matched_fields.map((field) => FIELD_LABELS[field] ?? field).join("・")}
          </span>
        )}
        <span className="ml-auto">更新 {formatDateTime(skill.updated_at)}</span>
      </div>
    </li>
  );
}

function EmptyState({ hasCondition }: { hasCondition: boolean }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
      <p className="text-slate-600">
        {hasCondition
          ? "条件に一致する Skills がありません。"
          : "まだ Skills が登録されていません。"}
      </p>
      {hasCondition && (
        <p className="mt-2 text-xs text-slate-500">
          検索語はすべてを含むもの（AND）で絞り込みます。語を減らすと広がります。
        </p>
      )}
      <Link
        href={hasCondition ? "/" : "/upload"}
        className="mt-4 inline-block rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        {hasCondition ? "条件をクリア" : "アップロードする"}
      </Link>
    </div>
  );
}
