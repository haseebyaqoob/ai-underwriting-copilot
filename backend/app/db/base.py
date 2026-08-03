"""
Declarative base shared by every model. Alembic's env.py imports
`Base.metadata` from here for autogeneration, and imports the `models`
package (see db/models/__init__.py) so every model is registered on that
metadata before autogenerate runs.
"""
from sqlalchemy.orm import DeclarativeBase

# A consistent naming convention means Alembic-generated constraint names
# are deterministic across autogenerate runs instead of random suffixes,
# which makes migration diffs sane to review.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    pass


Base.metadata.naming_convention = NAMING_CONVENTION
