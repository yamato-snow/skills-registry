import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

// next/font/google は雛形に入っていたが外した。ビルド時にフォントを
// ダウンロードしに行くため、Docker のビルドやネットワークの無い CI が
// 外部への到達性に依存してしまう。見た目のためにビルドの安定性を
// 落とす取引になっていないか、という判断でシステムフォントに寄せた。

export const metadata: Metadata = {
  title: "Skills Registry",
  description: "Skills パッケージの登録・検索・配布を行う社内向けレジストリ",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Skills Registry
            </Link>
            <nav className="flex items-center gap-4 text-sm">
              <Link href="/" className="text-slate-600 hover:text-slate-900">
                一覧
              </Link>
              <Link
                href="/upload"
                className="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-white hover:bg-slate-700"
              >
                アップロード
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
