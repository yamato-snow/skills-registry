# frontend のコンテナイメージ（マルチステージ）
#
# 3 段に分ける理由:
#   deps  … 依存のインストール。package.json が変わらない限りキャッシュが効く
#   build … Next.js のビルド。ソース変更のたびに走るが、依存の再取得はしない
#   runner… 実行に必要なものだけ。node_modules を丸ごと持ち込まない
#
# 2 段（build → runner）でも動くが、その場合ソースを 1 行変えるたびに
# npm ci からやり直しになる。deps を独立させておくと、そこだけ再利用できる。

# ---------------------------------------------------------------------------
# deps: 依存のインストールだけ
# ---------------------------------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app

# package.json と lockfile だけを先にコピーする（キャッシュのため）
COPY package.json package-lock.json ./

# npm install ではなく npm ci を使う。
#   - lockfile のとおりに厳密に入れる（install は lockfile を書き換えうる）
#   - node_modules を毎回作り直すので、前回の残骸が混ざらない
# 再現性が要るビルド環境では ci が正しい
RUN npm ci

# ---------------------------------------------------------------------------
# build: Next.js のビルド
# ---------------------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_ で始まる環境変数は **ビルド時にバンドルへ埋め込まれる**。
# 実行時に渡しても、ブラウザ向けのコードには反映されない（ADR-005）。
# だから build-arg として受け取り、この段階で env にしておく必要がある
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# 収集される匿名テレメトリを止める。ビルドが外部への到達性に依存しないように
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ---------------------------------------------------------------------------
# runner: 実行時
# ---------------------------------------------------------------------------
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    # 既定の localhost だとコンテナの外から到達できない
    HOSTNAME=0.0.0.0

# node イメージには既に node ユーザーがいるので、それを使う（非 root 実行）
USER node

# next.config.ts の output: "standalone" が生成する成果物。
# 起動に必要なファイルと、実際に使う node_modules だけが入っているので、
# ここをコピーするだけでよい（node_modules 全体を持ち込むと数百 MB 変わる）
COPY --from=build --chown=node:node /app/.next/standalone ./
# static と public は standalone に含まれないので個別にコピーする
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public

EXPOSE 3000

# standalone が吐く自前のサーバを起動する（next start ではない）
CMD ["node", "server.js"]
