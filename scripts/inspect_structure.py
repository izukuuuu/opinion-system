import os
import sys
from sqlalchemy import create_engine, text

# Add backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

# Connection string
DB_URL = "postgresql+psycopg2://postgres:w13135365248@101.43.204.229:5432/remote"

def inspect_structure():
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        print(f"Connected to: {engine.url.database}")
        
        # 1. List Schemas
        print("\n--- Schemas ---")
        schemas = conn.execute(text("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname != 'information_schema'")).fetchall()
        for s in schemas:
            print(f"- {s[0]}")
            
            # 2. List Tables in this Schema
            tables = conn.execute(text(f"SELECT tablename FROM pg_tables WHERE schemaname = '{s[0]}'")).fetchall()
            if tables:
                print(f"  Tables: {', '.join([t[0] for t in tables])}")
            else:
                print("  (No tables)")

if __name__ == "__main__":
    try:
        inspect_structure()
    except Exception as e:
        print(f"Error: {e}")
