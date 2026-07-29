"""ストレージの抽象（ADR-003）.

Protocol（構造的部分型）で定義しているので、実装クラスはこれを継承しなくてよい。
同じシグネチャを持つクラスであれば通るため、テスト用の偽実装を数行で書ける。

**ローカルファイルシステム固有の概念をここに漏らさない**のが設計上の要点。
get_path() のようなメソッドを 1 つ生やした瞬間に、S3 実装で対応物がなくなり
抽象が壊れる。将来の移行コストを「S3Storage を書く + DI を 1 行差し替える」に
閉じ込めるための境界である。
"""

from typing import BinaryIO, Protocol


class StorageBackend(Protocol):
    def save(self, key: str, data: bytes) -> None:
        """key の位置に data を保存する（既存なら上書き）."""
        ...

    def open(self, key: str) -> BinaryIO:
        """読み出し用のストリームを返す.

        bytes ではなくストリームを返すのは、ダウンロード時に 50MB を
        メモリへ全載せせず StreamingResponse へ流すため。
        """
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """key を削除する（存在しなくてもエラーにしない）.

        現時点の API からは呼ばれないが、design.md §6 の管理者ロール
        （版の削除）で必要になる。後から Protocol を広げるより、最初から
        定義しておくほうが実装漏れに気づきやすい。
        """
        ...
