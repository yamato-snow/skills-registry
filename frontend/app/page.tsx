/**
 * 一覧ページ。Server Component（ADR-005）。
 *
 * 表示するだけで「操作の途中状態」がないので Server のまま。データ取得は
 * サーバ内の URL で 1 往復で終わり、ローディング状態の実装が要らない。
 */

import Link from "next/link";

import { SearchForm } from "@/app/_components/SearchForm";
import { fetchSkillsFromServer, type SkillSummary } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type Props = {
  // Next.js 15 では searchParams が Promise で渡る
  searchParams: Promise<{ q?: string; tag?: string }>;
};

export default async function HomePage({ searchParams }: Props) {
  const { q = "", tag = "" } = await searchParams;
  const skills = await fetchSkillsFromServer({ q, tag });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Skills 一覧</h1>
          <p className="mt-1 text-sm text-slate-600">
            登録済みの Skills パッケージ {skills.length} 件{tag && ` / タグ「${tag}」で絞り込み中`}
          </p>
        </div>
        <SearchForm defaultQuery={q} defaultTag={tag} />
      </div>

      {skills.length === 0 ? (
        <EmptyState hasCondition={Boolean(q || tag)} />
      ) : (
        <ul className="grid gap-3">
          {skills.map((skill) => (
            <SkillCard key={skill.id} skill={skill} />
          ))}
        </ul>
      )}
    </div>
  );
}

function SkillCard({ skill }: { skill: SkillSummary }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-400">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            href={`/skills/${skill.id}`}
            className="font-semibold text-slate-900 hover:underline"
          >
            {skill.name}
          </Link>
          <p className="mt-1 text-sm text-slate-600">{skill.description}</p>
        </div>
        <span className="shrink-0 rounded bg-slate-100 px-2 py-1 text-xs text-slate-600">
          v{skill.latest_version}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {skill.tags.map((name) => (
          <Link
            key={name}
            href={`/?tag=${encodeURIComponent(name)}`}
            className="rounded-full bg-slate-100 px-2 py-0.5 hover:bg-slate-200"
          >
            #{name}
          </Link>
        ))}
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
      <Link
        href="/upload"
        className="mt-4 inline-block rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        アップロードする
      </Link>
    </div>
  );
}
