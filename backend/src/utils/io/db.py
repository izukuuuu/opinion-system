"""
数据库连接和查询模块
"""
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from typing import Optional, List, Dict, Any, Tuple
from ..setting.settings import settings
from ..logging.logging import setup_logger, log_success, log_error, log_module_start


class DatabaseManager:
    """数据库管理类"""
    
    def __init__(self, db_url: Optional[str] = None):
        """
        初始化数据库连接
        
        Args:
            db_url (Optional[str]): 数据库连接URL，如果为None则从配置读取
        """
        # 优先级：显式传入 > 环境变量 > databases.yaml > defaults.yaml
        env_url = settings.get('env.DB_URL')
        # 如果 env 中残留占位符（如 host/user），则忽略以免误连
        if isinstance(env_url, str) and env_url:
            lowered = env_url.lower()
            if '://user:pass@host' in lowered or '@host' in lowered or 'user:pass' in lowered:
                env_url = None

        # 从databases.yaml读取配置
        db_config = settings.get('databases', {})
        
        # 优先使用 active 指定的连接
        active_id = db_config.get('active')
        databases_url = None
        
        if active_id:
            connections = db_config.get('connections') or []
            if isinstance(connections, list):
                for conn in connections:
                    if isinstance(conn, dict) and conn.get('id') == active_id:
                        databases_url = conn.get('url')
                        break
        
        # 如果没有找到 active 连接（或者没有设置 active），尝试使用遗留的 db_url 字段
        if not databases_url:
            databases_url = db_config.get('db_url')

        # 如果仍然没有，尝试找第一个连接作为默认
        if not databases_url and isinstance(db_config.get('connections'), list) and db_config['connections']:
             first_conn = db_config['connections'][0]
             if isinstance(first_conn, dict):
                 databases_url = first_conn.get('url')

        self.db_url = db_url or env_url or databases_url or settings.get('defaults.db_url')
        self.engine: Optional[Engine] = None
        
    def connect(self) -> Engine:
        """
        创建数据库连接
        
        Returns:
            Engine: SQLAlchemy引擎
        """
        if self.engine is None:
            self.engine = create_engine(self.db_url)
        return self.engine

    def get_engine_for_database(self, database_name: str) -> Engine:
        """
        返回指向指定数据库的引擎（不会修改当前实例的 engine）
        
        Args:
            database_name (str): 数据库名称
        
        Returns:
            Engine: 指向指定数据库的引擎
        """
        base_url = make_url(self.db_url)
        db_url = base_url.set(database=database_name)
        return create_engine(db_url)

    def ensure_database(self, database_name: str) -> bool:
        """
        确保数据库存在，不存在则创建
        
        Args:
            database_name (str): 数据库名称
        
        Returns:
            bool: 是否成功
        """
        try:
            # Ensure we are connected to the server (no specific DB for creation)
            base_url = make_url(self.db_url).set(database=None)
            
            # For creation, we usually need isolation_level="AUTOCOMMIT" 
            # especially for Postgres which cannot CREATE DATABASE in a transaction block
            engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
            
            database_name_sanitized = database_name.replace("`", "").replace('"', "")
            dialect_name = engine.dialect.name

            with engine.connect() as conn:
                # Check if database exists first to avoid errors
                # (IF NOT EXISTS is not standard across all versions/dialects in the exact same way)
                exists = False
                if dialect_name == 'postgresql':
                    # Postgres check
                    result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{database_name_sanitized}'"))
                    exists = result.scalar() == 1
                elif dialect_name == 'mysql':
                    # MySQL check
                    result = conn.execute(text(f"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = '{database_name_sanitized}'"))
                    exists = bool(result.scalar())
                else:
                    # Fallback check
                    try:
                        conn.execute(text(f"USE {database_name_sanitized}"))
                        exists = True
                    except Exception:
                        exists = False

                if not exists:
                    if dialect_name == 'postgresql':
                         conn.execute(text(f'CREATE DATABASE "{database_name_sanitized}"'))
                    elif dialect_name == 'mysql':
                        conn.execute(text(
                            f"CREATE DATABASE IF NOT EXISTS `{database_name_sanitized}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                        ))
                    else:
                        # Fallback generic
                        conn.execute(text(f"CREATE DATABASE {database_name_sanitized}"))
            
            engine.dispose()
            return True
        except Exception as e:
            return False

    def drop_database(self, database_name: str) -> bool:
        """
        删除数据库
        
        Args:
            database_name (str): 数据库名称
        
        Returns:
            bool: 是否成功
        """
        try:
            # Connect to server (no specific DB)
            base_url = make_url(self.db_url).set(database=None)
            engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
            
            database_name_sanitized = database_name.replace("`", "").replace('"', "")
            dialect_name = engine.dialect.name

            with engine.connect() as conn:
                if dialect_name == 'postgresql':
                    # Postgres requires forcing disconnection of other users before dropping
                    try:
                         # 1. Disallow new connections to avoid race condition
                         conn.execute(text(f"UPDATE pg_database SET datallowconn = 'false' WHERE datname = '{database_name_sanitized}'"))
                         
                         # 2. Terminate existing connections
                         conn.execute(text(f"""
                            SELECT pg_terminate_backend(pid) 
                            FROM pg_stat_activity 
                            WHERE datname = '{database_name_sanitized}'
                            AND pid <> pg_backend_pid()
                         """))
                    except Exception as e:
                        print(f"DEBUG: Terminate connections failed/ignored: {e}")
                        pass 
                    
                    conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name_sanitized}"'))
                elif dialect_name == 'mysql':
                    conn.execute(text(f"DROP DATABASE IF EXISTS `{database_name_sanitized}`"))
                else:
                    conn.execute(text(f"DROP DATABASE IF EXISTS {database_name_sanitized}"))
            
            engine.dispose()
            return True
        except Exception as e:
            print(f"DEBUG: Drop database failed: {e}")
            # log failure if needed, or caller handles it
            return False
    
    def execute_query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """
        执行查询语句
        
        Args:
            query (str): SQL查询语句
            params (Optional[Dict]): 查询参数
        
        Returns:
            pd.DataFrame: 查询结果
        """
        engine = self.connect()
        with engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            return pd.DataFrame(result.fetchall(), columns=result.keys())
    
    def execute_update(self, query: str, params: Optional[Dict] = None) -> int:
        """
        执行更新语句
        
        Args:
            query (str): SQL更新语句
            params (Optional[Dict]): 更新参数
        
        Returns:
            int: 影响的行数
        """
        engine = self.connect()
        with engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            conn.commit()
            return result.rowcount
    
    def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        
        Args:
            table_name (str): 表名
        
        Returns:
            bool: 表是否存在
        """
        try:
            from sqlalchemy import inspect
            engine = self.connect()
            inspector = inspect(engine)
            return inspector.has_table(table_name)
        except Exception:
            # log or handle error
            return False
    
    def create_table(self, table_name: str, columns: List[Dict[str, str]]) -> bool:
        """
        创建表
        
        Args:
            table_name (str): 表名
            columns (List[Dict[str, str]]): 列定义列表，每个元素包含name和type
        
        Returns:
            bool: 是否创建成功
        """
        try:
            column_defs = []
            for col in columns:
                column_defs.append(f"{col['name']} {col['type']}")
            
            create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(column_defs)})"
            self.execute_update(create_sql)
            return True
        except Exception as e:
            return False
    
    def close(self):
        """
        关闭数据库连接
        """
        if self.engine:
            self.engine.dispose()
            self.engine = None


# 全局数据库管理器实例
db_manager = DatabaseManager()