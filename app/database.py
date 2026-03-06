from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, echo=False, pool_pre_ping=True)


def init_db() -> None:
    if settings.auto_create_schema or settings.app_env in {"dev", "test"}:
        SQLModel.metadata.create_all(engine)


def reset_db() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
