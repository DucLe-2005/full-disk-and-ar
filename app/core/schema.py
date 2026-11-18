from sqlalchemy import inspect, text

from app.core.database import Base, engine
from app.models.pipeline_job import PipelineJob
from app.models.prediction import PredictionRecord


def create_database_schema() -> None:
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # The API and forecast runner can initialize the same database concurrently.
            connection.execute(text("SELECT pg_advisory_xact_lock(83162041)"))
        Base.metadata.create_all(bind=connection)
        # create_all does not add columns to an existing installation.
        columns = {column["name"] for column in inspect(connection).get_columns("predictions")}
        if "observed_at" not in columns:
            connection.execute(text("ALTER TABLE predictions ADD COLUMN observed_at TIMESTAMP"))
        if "is_backfill" not in columns:
            connection.execute(text("ALTER TABLE predictions ADD COLUMN is_backfill BOOLEAN"))
