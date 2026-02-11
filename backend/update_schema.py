
from src.graph.neo4j_client import get_driver
from src.graph.schema import init_schema
import logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    driver = get_driver()
    init_schema(driver)
    print("Schema updated successfully.")
