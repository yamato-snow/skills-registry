import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker の runner ステージへコピーする量を最小にするための設定。
  // これを付けると .next/standalone に「起動に必要なファイルと node_modules の
  // 実際に使う分だけ」がまとめて出力される。付けないと node_modules を丸ごと
  // イメージへ持ち込むことになり、サイズが数百 MB 変わる。
  // Dockerfile 側の COPY と対で意味を持つ設定なので、両方にこのコメントを置く
  output: "standalone",
};

export default nextConfig;
