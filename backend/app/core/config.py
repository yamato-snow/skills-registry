"""アプリケーション設定.

設定値は **すべてここに集約する**。コードのあちこちに os.environ や既定値を
散らさないのは、ECS のタスク定義へ移すときに「何を注入すればよいか」が
このファイルだけで分かる状態を保つため（design.md §7）。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- DB ---
    # asyncpg ドライバを明示する（postgresql:// のままだと同期ドライバが選ばれる）
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/skills_registry"

    # --- ストレージ ---
    # LocalStorage の保存先。本番で S3Storage に差し替える際は不要になる（ADR-003）
    storage_dir: str = "./storage"

    # --- ZIP 検証の上限（ADR-002・値の根拠は ADR-008）---
    # 展開後の合計サイズ。zip bomb の遮断もこの値で行う。
    # 変えるときは 3 か所連動（生アップロード上限・展開後累積上限・ALB 経路設定）
    max_total_size: int = 50 * 1024 * 1024  # 50MB
    # ZIP 内のファイル数。展開しない設計（ADR-002 案 B）なのでサーバの inode は枯渇せず、
    # この上限が実際に守るのは (1) file_tree JSONB と詳細画面の肥大 —— とくにゼロバイト
    # ファイルの洪水は合計サイズでは検出できず件数でしか止められない ——
    # (2) 中継点としての責任（ダウンロードした人の手元での展開停止）の 2 つ。
    # 2000 は実在パッケージ最大 320 件を余裕をもって受け入れ、かつ node_modules 等の
    # 誤混入（典型的に 5,000 件〜）を手前で止める線として選んだ（ADR-008 論点 A）
    max_files: int = 2000
    # SKILL.md 単体の読み出し上限。ヘッダの file_size は自己申告なので、
    # 実際に解凍する量にも独立した上限を課す（＝解凍露出の総量そのもの・ADR-008 論点 B）
    max_skill_md_size: int = 1 * 1024 * 1024  # 1MB

    # --- CORS ---
    # ブラウザ（アップロード画面）から API を直接叩くため許可が要る（ADR-005）。
    # カンマ区切りで複数指定できる
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """設定はプロセス内で 1 度だけ読む（環境変数は起動後に変わらない前提）。"""
    return Settings()


settings = get_settings()
