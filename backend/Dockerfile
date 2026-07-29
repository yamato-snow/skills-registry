# backend のコンテナイメージ（マルチステージ）
#
# なぜマルチステージにするのか:
#   Python パッケージの中にはビルド時に C コンパイラを必要とするものがある
#   （asyncpg など）。ビルドに必要なだけの道具を最終イメージに残すと、
#   イメージが数百 MB 太り、かつ「コンテナ内でコンパイラが使える」という
#   攻撃者にとって都合のよい状態を配ってしまう。
#   builder で作ったものだけを runtime へ持ち込むことで、両方を避ける。

# ---------------------------------------------------------------------------
# builder: 依存を仮想環境へインストールする
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# 依存の解決とインストールに uv を使う。
# pip でも同じことはできるが、pip には「pyproject の依存だけを入れて
# プロジェクト自体はビルドしない」という指定がない。アプリのソースを
# コピーする前に依存だけを入れたい（＝レイヤキャッシュを効かせたい）ので、
# それが素直に書ける uv を選んだ。バージョンは固定する（再現性のため）
COPY --from=ghcr.io/astral-sh/uv:0.9.29 /uv /usr/local/bin/uv

# ビルドにだけ必要な道具。この層は最終イメージに含まれない
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    # apt のキャッシュを同じ RUN の中で消す。層は積み上げ式なので、
    # 別の RUN で消してもイメージサイズは減らない
    && rm -rf /var/lib/apt/lists/*

# 仮想環境を作って、そのディレクトリごと runtime へコピーする。
# システムの site-packages へ直接入れるより、持ち運ぶ範囲が明確になる
ENV VIRTUAL_ENV=/opt/venv
RUN uv venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# 依存の宣言だけを先にコピーする。
# アプリのソースを変更しても pyproject.toml が変わっていなければ、
# この層はキャッシュが効いて再インストールが走らない（ビルドが速い）
COPY pyproject.toml ./
RUN uv pip install --no-cache -r pyproject.toml

# ---------------------------------------------------------------------------
# runtime: 実行に必要なものだけ
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Python の実行時挙動をコンテナ向けに揃える
#   PYTHONDONTWRITEBYTECODE: .pyc を書かない（イメージが汚れるだけで再利用されない）
#   PYTHONUNBUFFERED: 標準出力をバッファしない。これがないとログが
#                     コンテナのログドライバへ届くのが遅れ、障害調査で困る
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# 非 root で動かす。コンテナが乗っ取られたときにできることを減らす。
# --system は対話ログイン不要のサービス用アカウントを作るオプション
RUN useradd --system --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appuser app ./app

# ZIP 原本の保存先。compose ではここにホストのディレクトリをマウントする。
# 先に作って所有者を移しておかないと、非 root のプロセスが書き込めない
RUN mkdir -p /data/storage && chown -R appuser:appuser /data

USER appuser

EXPOSE 8000

# --host 0.0.0.0 が必須。既定の 127.0.0.1 だとコンテナの外（他のコンテナや
# ホスト）から到達できず、「起動しているのに繋がらない」状態になる
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
