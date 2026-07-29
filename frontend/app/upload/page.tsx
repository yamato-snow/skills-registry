"use client";

/**
 * アップロードページ。Client Component（ADR-005）。
 *
 * なぜここだけ Client なのか: ドラッグ中・ファイル選択中・送信中という
 * 3 つの「ユーザー操作の途中状態」を持つ必要があるため。これらは本質的に
 * ブラウザ側の状態で、サーバには持てない。
 *
 * POST はブラウザから FastAPI へ直接投げる。Server Action を挟むと
 * ファイルの実体が Next.js サーバを 1 ホップ余計に通る。
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { uploadSkillFromBrowser, type UploadResult } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  function selectFile(next: File | null) {
    setFile(next);
    setError(null);
    setResult(null);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || isSubmitting) return;

    setIsSubmitting(true);
    setError(null);
    try {
      const uploaded = await uploadSkillFromBrowser(file);
      setResult(uploaded);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      // 一覧は Server Component なので、サーバ側の取得をやり直させる
      router.refresh();
    } catch (caught) {
      // API が返す日本語の detail をそのまま出す
      setError(caught instanceof Error ? caught.message : "アップロードに失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Skills をアップロード</h1>
        <p className="mt-1 text-sm text-slate-600">
          ルート直下、または 1 階層下に <code className="font-mono">SKILL.md</code> を含む ZIP
          を選んでください。同じ名前の Skills は新しい版として登録されます。
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragging(false);
            const dropped = event.dataTransfer.files?.[0];
            if (dropped) selectFile(dropped);
          }}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition ${
            isDragging ? "border-slate-900 bg-slate-100" : "border-slate-300 bg-white"
          }`}
        >
          <p className="text-sm text-slate-600">
            ここに ZIP をドラッグ＆ドロップ、またはクリックして選択
          </p>
          {file && (
            <p className="mt-3 font-mono text-sm text-slate-900">
              {file.name}（{(file.size / 1024).toFixed(1)} KB）
            </p>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
          />
        </div>

        <button
          type="submit"
          disabled={!file || isSubmitting}
          className="w-full rounded-md bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isSubmitting ? "アップロード中…" : "アップロード"}
        </button>
      </form>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      {result && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <p>
            <span className="font-semibold">{result.name}</span> を v{result.version} として
            {result.created ? "登録" : "更新"}しました。
          </p>
          <Link href={`/skills/${result.id}`} className="mt-1 inline-block underline">
            詳細を見る
          </Link>
        </div>
      )}
    </div>
  );
}
