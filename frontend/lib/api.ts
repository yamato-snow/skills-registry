/**
 * API クライアント（ADR-005）。
 *
 * このファイルの存在理由は「同じ API なのに、実行される場所によって URL が
 * 違う」という事実を 1 箇所に閉じ込めることにある。
 *
 *   Server Component から → http://backend:8000  （compose のネットワーク内）
 *   ブラウザから           → http://localhost:8000（ホストに公開されたポート）
 *
 * 取り違えたときの症状は分かりにくい（コンテナ内から localhost を叩いて接続
 * 拒否 / ブラウザから backend を叩いて名前解決失敗）ので、関数名に
 * FromServer / FromBrowser を入れて、呼ぶ側が気づけるようにしている。
 *
 * NEXT_PUBLIC_ 接頭辞の有無がそのまま「ブラウザに露出するか」を意味する
 * （Next.js の規約）。命名だけで用途が判別できる。
 */

const INTERNAL_API_URL = process.env.INTERNAL_API_URL ?? "http://backend:8000";
const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type FileEntry = {
  path: string;
  size: number;
};

export type SkillVersion = {
  version: number;
  size_bytes: number;
  created_at: string;
};

export type SkillSummary = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  latest_version: number;
  updated_at: string;
  // なぜこの Skill が出てきたか（ADR-006）。q 未指定なら空配列 / null
  matched_fields: string[];
  snippet: string | null;
};

export type SkillDetail = Omit<SkillSummary, "matched_fields" | "snippet"> & {
  // 最新版の SKILL.md 全文（ADR-007）
  skill_md_body: string;
  file_tree: FileEntry[];
  versions: SkillVersion[];
};

export type UploadResult = {
  id: string;
  name: string;
  version: number;
  created: boolean;
};

/** ブラウザから使うダウンロード URL（<a href> に入れる）。 */
export function downloadUrlFromBrowser(skillId: string, version?: number): string {
  const query = version === undefined ? "" : `?version=${version}`;
  return `${PUBLIC_API_URL}/skills/${skillId}/download${query}`;
}

async function getFromServer<T>(path: string): Promise<T> {
  const response = await fetch(`${INTERNAL_API_URL}${path}`, {
    // アップロード直後に一覧へ反映されることを優先する。プロトタイプの規模では
    // キャッシュによる性能上の利得より「登録したのに出てこない」混乱のほうが高くつく
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API エラー (${response.status}): ${path}`);
  }
  return (await response.json()) as T;
}

/** 一覧・検索（Server Component から呼ぶ）。`tags` は繰り返しパラメータで AND。 */
export async function fetchSkillsFromServer(params: {
  q?: string;
  tags?: string[];
}): Promise<SkillSummary[]> {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  for (const tag of params.tags ?? []) query.append("tag", tag);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getFromServer<SkillSummary[]>(`/skills${suffix}`);
}

/** 詳細（Server Component から呼ぶ）。見つからなければ null。 */
export async function fetchSkillFromServer(skillId: string): Promise<SkillDetail | null> {
  const response = await fetch(`${INTERNAL_API_URL}/skills/${skillId}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`API エラー (${response.status})`);
  }
  return (await response.json()) as SkillDetail;
}

/**
 * アップロード（Client Component から＝ブラウザから呼ぶ）。
 *
 * Server Action を経由させない理由: ファイルの実体が
 * ブラウザ → Next.js サーバ → FastAPI と 2 ホップし、50MB を Next.js の
 * メモリに一度載せることになる。中継する必要がないので直接投げる。
 */
export async function uploadSkillFromBrowser(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${PUBLIC_API_URL}/skills`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    // API は検証エラーを日本語の detail で返す。そのまま画面に出せる
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `アップロードに失敗しました (${response.status})`);
  }
  return (await response.json()) as UploadResult;
}
