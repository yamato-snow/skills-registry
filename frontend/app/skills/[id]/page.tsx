/**
 * 詳細ページ。Server Component（ADR-005）。読み取りのみで途中状態がない。
 *
 * SKILL.md の本文プレビュー（ADR-007）もここに置く。`react-markdown` の
 * 既定エクスポートは hooks を使わない同期コンポーネントなので、
 * Server Component のまま描画できる（`MarkdownHooks` のほうは CC 専用）。
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import Markdown from "react-markdown";

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
        <h2 className="mb-3 text-sm font-semibold text-slate-700">SKILL.md</h2>
        <SkillMarkdown body={skill.skill_md_body} />
      </section>

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

/**
 * SKILL.md の Markdown プレビュー。
 *
 * **XSS 対策は「サニタイズする」ではなく「危険な経路を作らない」で行う**
 * （ADR-002 と同じ考え方）。`rehype-raw` を入れないと、本文中の生 HTML は
 * パースされずテキストノードとして扱われるのが react-markdown の既定動作で、
 * `<script>alert(1)</script>` はそのまま文字として表示される。
 * `dangerouslySetInnerHTML` はこのプロジェクトのどこでも使わない。
 *
 * 見出し・リストのスタイルは `components` で明示している。Tailwind の
 * preflight が既定のマージンや箇条書きを消すので、何も当てないと
 * すべてが同じ大きさの平文になってしまうため。
 */
function SkillMarkdown({ body }: { body: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-5 py-4 text-sm break-words text-slate-700">
      <Markdown
        components={{
          h1: (props) => <h1 className="mt-4 mb-2 text-xl font-bold first:mt-0" {...props} />,
          h2: (props) => <h2 className="mt-4 mb-2 text-lg font-semibold first:mt-0" {...props} />,
          h3: (props) => <h3 className="mt-3 mb-2 font-semibold first:mt-0" {...props} />,
          p: (props) => <p className="my-2 leading-relaxed" {...props} />,
          ul: (props) => <ul className="my-2 list-disc space-y-1 pl-6" {...props} />,
          ol: (props) => <ol className="my-2 list-decimal space-y-1 pl-6" {...props} />,
          blockquote: (props) => (
            <blockquote
              className="my-2 border-l-2 border-slate-300 pl-3 text-slate-600"
              {...props}
            />
          ),
          code: (props) => (
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs" {...props} />
          ),
          pre: (props) => (
            <pre className="my-2 overflow-x-auto rounded bg-slate-100 p-3 text-xs" {...props} />
          ),
          hr: (props) => <hr className="my-4 border-slate-200" {...props} />,
          a: (props) => (
            // 外部リンクを新しいタブで開く。rel は tabnabbing の予防
            <a
              className="text-slate-900 underline"
              target="_blank"
              rel="noopener noreferrer"
              {...props}
            />
          ),
        }}
      >
        {body}
      </Markdown>
    </div>
  );
}
