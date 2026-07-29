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

    # --- ZIP 検証の上限（ADR-002）---
    # 展開後の合計サイズ。zip bomb の遮断もこの値で行う
    max_total_size: int = 50 * 1024 * 1024  # 50MB
    # ZIP 内のファイル数。極小ファイル大量投入による走査コストの爆発を防ぐ
    max_files: int = 500
    # SKILL.md 単体の読み出し上限。ヘッダの file_size は自己申告なので、
    # 実際に解凍する量にも独立した上限を課す
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
