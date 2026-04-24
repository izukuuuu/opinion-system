from __future__ import annotations
import logging
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import hashlib

from .neo4j_client import get_driver, get_session
from ..utils.setting.env_loader import get_api_key

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

LOG = logging.getLogger(__name__)

def parse_time(t_str: str) -> Optional[datetime]:
    if not t_str: return None
    # Try common formats
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(str(t_str), fmt)
        except ValueError:
            continue
    return None

def generate_event_summary(posts: List[Dict], topic_name: str) -> Dict[str, str]:
    """
    Use LLM to summarize the event.
    Returns: {"name": "Event Title", "summary": "Event Summary"}
    """
    if not posts:
        return {"name": f"事件_{topic_name}", "summary": ""}

    # Use first 10 posts for summary to save tokens
    context = "\n".join([f"- {p.get('title', '')}: {str(p.get('content', ''))[:100]}" for p in posts[:10]])
    
    api_key = get_api_key()
    if not api_key or OpenAI is None:
        return {"name": f"事件_{topic_name}_{posts[0].get('published_at', '')}", "summary": context[:200]}

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        prompt = f"""
请根据以下属于同一时间段和主题的帖子，总结为一个具体的事件。

主题: {topic_name}
帖子列表:
{context}

请输出 JSON 格式:
{{
    "name": "简短的事件标题 (不超过15字)",
    "summary": "事件摘要 (不超过100字)"
}}
"""
        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=[{'role': 'user', 'content': prompt}],
            response_format={"type": "json_object"}
        )
        content = completion.choices[0].message.content
        data = json.loads(content)
        return data
    except Exception as e:
        LOG.error(f"Event summary failed: {e}")
        return {"name": f"事件_{topic_name}", "summary": ""}

def cluster_and_link_events(project_topic: str, time_threshold_hours: int = 24) -> int:
    """
    Cluster posts in a topic into events based on time gaps.
    """
    driver = get_driver()
    event_count = 0
    
    with get_session() as session:
        # 1. Find all macro topics for the project
        result = session.run(
            "MATCH (t:Topic {project: $project, level: 'macro'}) RETURN t.id as tid, t.name as name",
            {"project": project_topic}
        )
        topics = [{"id": r["tid"], "name": r["name"]} for r in result]
        
        LOG.info(f"找到 {len(topics)} 个宏观话题进行事件聚类 (Found {len(topics)} topics to cluster events for project {project_topic}).")

        for i, topic in enumerate(topics):
            tid = topic["id"]
            tname = topic["name"]
            
            print(f"正在处理话题 [{i+1}/{len(topics)}]: {tname} (Processing topic {tname})...")
            
            p_result = session.run(
                """
                MATCH (p:Post)-[:ABOUT_TOPIC]->(t:Topic {id: $tid})
                RETURN DISTINCT p.id as pid, p.title as title, p.contents as content, p.published_at as published_at
                """,
                {"tid": tid}
            )
            posts = [dict(r) for r in p_result]
            
            if not posts:
                continue

            # 3. Sort by time
            valid_posts = []
            for p in posts:
                dt = parse_time(p.get("published_at"))
                if dt:
                    p["dt"] = dt
                    valid_posts.append(p)
            
            valid_posts.sort(key=lambda x: x["dt"])
            
            if not valid_posts:
                continue
                
            # 4. Cluster
            clusters = []
            current_cluster = [valid_posts[0]]
            
            for i in range(1, len(valid_posts)):
                prev = valid_posts[i-1]
                curr = valid_posts[i]
                diff = curr["dt"] - prev["dt"]
                
                if diff > timedelta(hours=time_threshold_hours):
                    clusters.append(current_cluster)
                    current_cluster = []
                
                current_cluster.append(curr)
            
            if current_cluster:
                clusters.append(current_cluster)
            
            LOG.info(f"Topic {tname} has {len(clusters)} events.")
            
            # 5. Create Events
            for idx, cluster in enumerate(clusters):
                # Generate summary
                meta = generate_event_summary(cluster, tname)
                event_name = meta.get("name") or f"{tname}_事件_{idx+1}"
                event_summary = meta.get("summary", "")
                
                # Unique ID for event
                start_str = str(cluster[0]["dt"])
                event_hash = hashlib.md5(f"{tid}_{idx}_{start_str}".encode()).hexdigest()[:8]
                event_id = f"{tid}_event_{event_hash}"
                
                # Create Event Node & Link Topic -> Event
                session.run(
                    """
                    MATCH (t:Topic {id: $tid})
                    MERGE (e:Event {id: $eid})
                    SET e.name = $name, 
                        e.summary = $summary, 
                        e.start_time = $start,
                        e.end_time = $end,
                        e.topic_id = $tid,
                        e.project = $project
                    MERGE (t)-[:HAS_EVENT]->(e)
                    """,
                    {
                        "tid": tid,
                        "eid": event_id,
                        "name": event_name,
                        "summary": event_summary,
                        "start": str(cluster[0]["dt"]),
                        "end": str(cluster[-1]["dt"]),
                        "project": project_topic
                    }
                )
                
                # Link Event -> Post and Remove Post -> Topic
                pids = [p["pid"] for p in cluster]
                session.run(
                    """
                    MATCH (e:Event {id: $eid})
                    MATCH (p:Post) WHERE p.id IN $pids
                    MERGE (e)-[:CONTAINS]->(p)
                    WITH p, e
                    MATCH (p)-[r:ABOUT_TOPIC]->(:Topic)
                    DELETE r
                    """,
                    {"eid": event_id, "pids": pids}
                )
                event_count += 1
                
    return event_count
