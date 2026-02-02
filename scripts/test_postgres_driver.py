import sys
from sqlalchemy import create_engine
import importlib

print(f"Python version: {sys.version}")

try:
    import psycopg2
    print("SUCCESS: psycopg2 imported successfully")
except ImportError as e:
    print(f"ERROR: Failed to import psycopg2: {e}")

try:
    # Just create the engine, don't connect yet to avoid network issues flagging as driver issues
    # But we need to use the postgresql+psycopg2 dialect
    engine = create_engine("postgresql+psycopg2://user:pass@localhost:5432/db")
    # Try to access the dialect to ensure the driver is loaded logic
    dialect = engine.dialect
    print(f"SUCCESS: SQLAlchemy engine created with dialect: {dialect.name}")
except Exception as e:
    print(f"ERROR: Failed to create SQLAlchemy engine: {e}")
