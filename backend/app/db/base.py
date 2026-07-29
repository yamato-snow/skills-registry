"""宣言的マッピングの基底クラス.

models.py と分けているのは循環 import を避けるため（session.py も create_all の
ために Base を必要とするが、models.py 全体を読む必要はない）。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
