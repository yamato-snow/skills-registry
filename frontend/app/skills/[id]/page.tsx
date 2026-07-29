/**
 * 詳細ページ。Server Component（ADR-005）。読み取りのみで途中状態がない。
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { downloadUrlFromBrowser, fetchSkillFromServer } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function SkillDetailPage({ params }: Props) {
  const { id } = await params;
  const skill = await fetchSkillFromServer(id);
  if (!skill) {
    notFound();
  }

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-slate-500 hover:text-slate-800">
          ← 一覧へ戻る
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{skill.name}</h1>
            <p className="mt-1 text-slate-600">{skill.description}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
              {skill.tags.map((name) => (
                <Link
                  key={name}
                  href={`/?tag=${encodeURIComponent(name)}`}
                  className="rounded-full bg-slate-100 px-2 py-0.5 hover:bg-slate-200"
                >
                  #{name}
                </Link>
              ))}
            </div>
          </div>
          {/*
            ダウンロードは <a href> で API へ直接。fetch でバイト列を取ってから
            Blob URL を作る方法もあるが、50MB をブラウザのメモリに載せる理由がない
          */}
          <a
            href={downloadUrlFromBrowser(skill.id)}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            最新版 (v{skill.latest_version}) をダウンロード
          </a>
        </div>
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">ファイル構成</h2>
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white">
          {skill.file_tree.map((entry) => (
            <li
              key={entry.path}
              className="flex items-center justify-between gap-4 px-4 py-2 text-sm"
            >
              <span className="truncate font-mono text-slate-700">{entry.path}</span>
              <span className="shrink-0 text-xs text-slate-500">{formatBytes(entry.size)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">版履歴</h2>
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white">
          {skill.versions.map((version) => (
            <li
              key={version.version}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 text-sm"
            >
              <span className="font-medium">v{version.version}</span>
              <span className="text-xs text-slate-500">
                {formatDateTime(version.created_at)} / {formatBytes(version.size_bytes)}
              </span>
              <a
                href={downloadUrlFromBrowser(skill.id, version.version)}
                className="text-xs text-slate-600 underline hover:text-slate-900"
              >
                ダウンロード
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
