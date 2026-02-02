import os
import sys
from sqlalchemy import create_engine, text

# Add backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

# Connection string
DB_URL = "postgresql+psycopg2://postgres:w13135365248@101.43.204.229:5432/remote"

def deep_inspect():
    engine = create_engine(DB_URL)
    with open('db_structure.txt', 'w', encoding='utf-8') as f:
        with engine.connect() as conn:
            f.write(f"Current Connection DB: {engine.url.database}\n")
            
            f.write("\n=== 1. ALL DATABASES on Server (pg_database) ===\n")
            dbs = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false")).fetchall()
            for db in dbs:
                f.write(f"- {db[0]}\n")

            f.write("\n=== 2. SCHEMAS in 'remote' (pg_namespace) ===\n")
            # List all schemas
            schemas = conn.execute(text("SELECT nspname FROM pg_namespace")).fetchall()
            for s_row in schemas:
                s = s_row[0]
                f.write(f"\n[Schema: {s}]\n")
                
                # Tables
                tables = conn.execute(text(f"SELECT tablename FROM pg_tables WHERE schemaname = '{s}'")).fetchall()
                if tables:
                    f.write(f"  Tables ({len(tables)}): {', '.join([t[0] for t in tables])}\n")
                else:
                    f.write("  (No tables)\n")
    print("Inspection complete. Check db_structure.txt")

if __name__ == "__main__":
    try:
        deep_inspect()
    except Exception as e:
        print(f"Error: {e}")
