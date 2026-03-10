from datetime import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.topic.data_bertopic_qwen_v2 import run_topic_bertopic

print(f"[START] {datetime.now().isoformat()}")
ok = run_topic_bertopic(
    topic="2025控烟舆情",
    start_date="2025-01-01",
    end_date="2025-12-31",
    bucket_topic="20260304-091855-2025控烟舆情",
    db_topic="2025控烟舆情",
    display_topic="2025控烟舆情",
)
print(f"[END] {datetime.now().isoformat()} success={ok}")
