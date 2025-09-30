# database/engine.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def make_engine(db_url: str, echo: bool = False):
    engine = create_engine(
        db_url,
        echo=echo,
        future=True,
        connect_args=(
            {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        ),
    )
    if db_url.startswith("sqlite"):
        _apply_sqlite_pragmas(engine)
    return engine


def _apply_sqlite_pragmas(engine):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=2000;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.close()


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
