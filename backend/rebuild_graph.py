import sys
import os
import logging
from pathlib import Path

# Add src to sys.path
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

from src.graph.sync_mysql_to_neo4j import sync_after_upload
from src.graph.topic_sync import sync_bertopic_results
from src.graph.neo4j_client import get_driver
from src.utils.setting.paths import bucket
from src.utils.logging.logging import setup_logger

def clean_project_data(project_topic: str):
    """
    Delete all nodes and relationships associated with the project topic.
    """
    driver = get_driver()
    with driver.session() as session:
        print(f"Cleaning existing data for project: {project_topic}...")
        
        # Delete Post, Account, Entity, Claim, Frame, Event, Chunk, Topic, SourceDoc
        # We assume they all have a 'topic' or 'project' property matching project_topic
        # Note: SourceDoc might be shared, so be careful. 
        # But in entity_extraction.py, SourceDoc doesn't seem to have a topic property!
        # And Entity/Claim IDs are hashed from content, so they might be shared across projects if content is identical?
        # But entity_extraction.py sets `e.topic = $topic`.
        
        # 1. Delete nodes with 'topic' property
        query_topic = """
        MATCH (n) WHERE n.topic = $topic
        DETACH DELETE n
        """
        session.run(query_topic, {"topic": project_topic})
        
        # 2. Delete nodes with 'project' property (used in topic_sync.py)
        query_project = """
        MATCH (n) WHERE n.project = $project
        DETACH DELETE n
        """
        session.run(query_project, {"project": project_topic})
        
        print("Clean complete.")

def rebuild_graph(project_topic: str, date_range: str, clean: bool = True):
    logger = setup_logger(project_topic, date_range)
    logger.info(f"Starting graph reconstruction for project: {project_topic}, date: {date_range}")

    if clean:
        clean_project_data(project_topic)

    # 1. Sync Basic Graph (Post, Account, Entity, Claim, etc.)
    logger.info("Step 1: Syncing basic graph structure...")
    try:
        # dataset_name usually matches project_topic for the DB name or logic
        result = sync_after_upload(
            topic=project_topic,
            date=date_range,
            dataset_name=None, 
            logger=logger,
            init_schema_if_missing=True,
            enable_entity_extraction=True,
            enable_chunk_embedding=True,
            source_bucket="filter"
        )
        logger.info(f"Step 1 Result: {result}")
    except Exception as e:
        logger.error(f"Step 1 failed: {e}")

    # 2. Sync BERTopic
    logger.info("Step 2: Syncing BERTopic results...")
    topic_output_dir = bucket("topic", project_topic, date_range)
    if topic_output_dir.exists():
        try:
            success = sync_bertopic_results(
                project_topic=project_topic,
                output_dir=topic_output_dir,
                clear_existing=False # Already cleaned if clean=True
            )
            if success:
                logger.info("BERTopic sync successful.")
            else:
                logger.error("BERTopic sync failed.")
        except Exception as e:
            logger.error(f"Step 2 failed: {e}")
    else:
        logger.warning(f"BERTopic output directory not found: {topic_output_dir}")

    logger.info("Graph reconstruction process finished.")

if __name__ == "__main__":
    # Default values based on your environment
    default_project = "新建专题"
    default_date = "2025-09-23_2025-09-23"
    
    print("Graph Reconstruction Tool")
    print("-------------------------")
    print(f"Default Project: {default_project}")
    print(f"Default Date: {default_date}")
    
    project = input(f"Enter project name (Press Enter for default): ").strip() or default_project
    date_str = input(f"Enter date/range (Press Enter for default): ").strip() or default_date
    
    clean_input = input("Clean existing data for this project? (y/n, default: y): ").strip().lower()
    clean = clean_input != 'n'
    
    rebuild_graph(project, date_str, clean)
