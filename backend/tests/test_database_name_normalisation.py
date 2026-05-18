import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fetch.data_fetch import _normalise_db_topic
from src.utils.io.db import DatabaseManager


def test_database_name_normalisation_discards_quote_punctuation() -> None:
    raw = '广州长隆大熊猫“家和” 婷仔"健康状况问题'

    assert DatabaseManager.normalise_database_name(raw) == "广州长隆大熊猫家和-婷仔健康状况问题"


def test_project_prefixed_topic_uses_same_physical_database_name() -> None:
    raw = '20260515-074058-广州长隆大熊猫-家和-婷仔-"健康状况问题"'

    assert _normalise_db_topic(raw) == "广州长隆大熊猫-家和-婷仔-健康状况问题"


def test_database_name_normalisation_keeps_postgres_byte_limit() -> None:
    raw = "非常长的专题名称" * 20
    normalised = DatabaseManager.normalise_database_name(raw)

    assert len(normalised.encode("utf-8")) <= 63
    assert normalised.endswith("-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8])
