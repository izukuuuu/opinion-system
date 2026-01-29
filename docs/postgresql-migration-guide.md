# PostgreSQL 迁移设计文档

## 目录

1. [概述](#概述)
2. [数据库 Schema 设计](#数据库-schema-设计)
3. [迁移策略](#迁移策略)
4. [Ubuntu 部署 PostgreSQL](#ubuntu-部署-postgresql)
5. [后端 API 适配](#后端-api-适配)
6. [前端统一改造](#前端统一改造)

---

## 概述

### 当前问题

| 模块 | 数据源 | 标识符 | 持久化 |
|------|--------|--------|--------|
| 本地项目管理 | useActiveProject | project.name/id/slug | localStorage |
| 远程数据缓存 | 独立 selectedTopic | topic (数据库名) | 无 |
| 基础分析 | useBasicAnalysis | topic (数据库名) | 无 |

**核心矛盾**：本地项目与远程专题之间没有映射关系，导致用户在不同模块间切换时需要重复选择。

### 迁移目标

1. 统一项目与专题的管理
2. 建立本地项目 ↔ 远程专题的映射关系
3. 为后续功能扩展（多用户、权限管理）打下基础

---

## 数据库 Schema 设计

### 表结构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      PostgreSQL                              │
├─────────────────────────────────────────────────────────────┤
│  projects (项目表)                                           │
│  ├── id              UUID PRIMARY KEY                       │
│  ├── name            VARCHAR(255) UNIQUE NOT NULL           │
│  ├── slug            VARCHAR(255) UNIQUE NOT NULL           │
│  ├── display_name    VARCHAR(255)                           │
│  ├── description     TEXT                                   │
│  ├── metadata        JSONB DEFAULT '{}'                     │
│  ├── created_at      TIMESTAMP DEFAULT NOW()                │
│  └── updated_at      TIMESTAMP DEFAULT NOW()                │
├─────────────────────────────────────────────────────────────┤
│  remote_topics (远程专题表)                                  │
│  ├── id              UUID PRIMARY KEY                       │
│  ├── project_id      UUID REFERENCES projects(id)           │
│  ├── topic_name      VARCHAR(255) NOT NULL                  │
│  ├── display_name    VARCHAR(255)                           │
│  ├── source_type     VARCHAR(50) DEFAULT 'mongodb'          │
│  ├── connection_info JSONB                                  │
│  ├── metadata        JSONB DEFAULT '{}'                     │
│  ├── is_active       BOOLEAN DEFAULT true                   │
│  ├── last_synced_at  TIMESTAMP                              │
│  ├── created_at      TIMESTAMP DEFAULT NOW()                │
│  └── updated_at      TIMESTAMP DEFAULT NOW()                │
├─────────────────────────────────────────────────────────────┤
│  topic_mappings (专题映射表 - 过渡期使用)                     │
│  ├── id              UUID PRIMARY KEY                       │
│  ├── local_project   VARCHAR(255) NOT NULL                  │
│  ├── remote_topic    VARCHAR(255) NOT NULL                  │
│  ├── mapping_type    VARCHAR(50) DEFAULT 'manual'           │
│  ├── notes           TEXT                                   │
│  ├── created_at      TIMESTAMP DEFAULT NOW()                │
│  └── UNIQUE(local_project, remote_topic)                    │
├─────────────────────────────────────────────────────────────┤
│  migration_logs (迁移日志表)                                 │
│  ├── id              UUID PRIMARY KEY                       │
│  ├── operation       VARCHAR(100) NOT NULL                  │
│  ├── source_type     VARCHAR(50)                            │
│  ├── target_type     VARCHAR(50)                            │
│  ├── record_count    INTEGER DEFAULT 0                      │
│  ├── status          VARCHAR(20) DEFAULT 'pending'          │
│  ├── error_message   TEXT                                   │
│  ├── started_at      TIMESTAMP DEFAULT NOW()                │
│  └── completed_at    TIMESTAMP                              │
└─────────────────────────────────────────────────────────────┘
```

### SQL 建表语句

```sql
-- 启用 UUID 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 项目表
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 远程专题表
CREATE TABLE remote_topics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    topic_name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    source_type VARCHAR(50) DEFAULT 'mongodb',
    connection_info JSONB,
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    last_synced_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TRIGGER update_remote_topics_updated_at
    BEFORE UPDATE ON remote_topics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 专题映射表（过渡期）
CREATE TABLE topic_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    local_project VARCHAR(255) NOT NULL,
    remote_topic VARCHAR(255) NOT NULL,
    mapping_type VARCHAR(50) DEFAULT 'manual',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(local_project, remote_topic)
);

-- 迁移日志表
CREATE TABLE migration_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation VARCHAR(100) NOT NULL,
    source_type VARCHAR(50),
    target_type VARCHAR(50),
    record_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- 索引
CREATE INDEX idx_remote_topics_project_id ON remote_topics(project_id);
CREATE INDEX idx_remote_topics_topic_name ON remote_topics(topic_name);
CREATE INDEX idx_topic_mappings_local_project ON topic_mappings(local_project);
CREATE INDEX idx_topic_mappings_remote_topic ON topic_mappings(remote_topic);
CREATE INDEX idx_migration_logs_status ON migration_logs(status);
```

---

## 迁移策略

### 阶段一：本地映射管理（当前实现）

在 PostgreSQL 部署前，先在前端实现本地映射管理：

1. **保存远端数据库快照到本地**
   - 从 MongoDB 获取所有专题列表
   - 保存到本地 JSON 文件或 localStorage

2. **建立映射关系**
   - 手动或自动匹配本地项目与远程专题
   - 映射数据暂存本地

3. **导出迁移数据**
   - 生成 SQL 插入语句
   - 或导出 JSON 格式供后续导入

### 阶段二：PostgreSQL 部署后

1. 执行建表 SQL
2. 导入映射数据
3. 修改后端 API 连接 PostgreSQL
4. 前端切换到新 API

---

## Ubuntu 部署 PostgreSQL

### 方式一：直接安装（推荐用于生产环境）

```bash
# 1. 更新系统包
sudo apt update && sudo apt upgrade -y

# 2. 安装 PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# 3. 检查服务状态
sudo systemctl status postgresql

# 4. 启动并设置开机自启
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 5. 切换到 postgres 用户
sudo -i -u postgres

# 6. 进入 PostgreSQL 命令行
psql

# 7. 创建数据库和用户
CREATE USER opinion_admin WITH PASSWORD 'your_secure_password';
CREATE DATABASE opinion_system OWNER opinion_admin;
GRANT ALL PRIVILEGES ON DATABASE opinion_system TO opinion_admin;

# 8. 退出
\q
exit
```

### 方式二：Docker 安装（推荐用于开发/测试）

```bash
# 1. 安装 Docker（如未安装）
sudo apt install docker.io docker-compose -y
sudo systemctl start docker
sudo systemctl enable docker

# 2. 创建 docker-compose.yml
cat > ~/opinion-postgres/docker-compose.yml << 'EOF'
version: '3.8'
services:
  postgres:
    image: postgres:15
    container_name: opinion_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: opinion_admin
      POSTGRES_PASSWORD: your_secure_password
      POSTGRES_DB: opinion_system
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql

volumes:
  postgres_data:
EOF

# 3. 启动容器
cd ~/opinion-postgres
docker-compose up -d

# 4. 查看日志
docker-compose logs -f postgres
```

### 配置远程访问

```bash
# 1. 编辑 postgresql.conf
sudo nano /etc/postgresql/15/main/postgresql.conf

# 找到并修改：
listen_addresses = '*'

# 2. 编辑 pg_hba.conf
sudo nano /etc/postgresql/15/main/pg_hba.conf

# 添加一行（允许特定 IP 或网段）：
host    opinion_system    opinion_admin    0.0.0.0/0    md5

# 3. 重启 PostgreSQL
sudo systemctl restart postgresql

# 4. 开放防火墙端口
sudo ufw allow 5432/tcp
```

### 连接测试

```bash
# 本地连接
psql -U opinion_admin -d opinion_system -h localhost

# 远程连接（从开发机）
psql -U opinion_admin -d opinion_system -h your_server_ip
```

---

## 后端 API 适配

### Python 依赖

```bash
pip install psycopg2-binary sqlalchemy
```

### 连接配置示例

```python
# backend/config/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://opinion_admin:your_secure_password@localhost:5432/opinion_system'
)

engine = create_engine(POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 前端统一改造

### 改造目标

1. 所有模块使用 `useActiveProject` 作为唯一项目状态源
2. 通过 `project.remoteTopics` 获取关联的远程专题
3. 统一的专题选择器组件

### 改造后的数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    useActiveProject                          │
│  ├── activeProject (当前选中的项目)                          │
│  ├── activeProject.remoteTopics[] (关联的远程专题)           │
│  └── activeRemoteTopic (当前选中的远程专题)                  │
└─────────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ 本地数据  │    │ 远程缓存  │    │ 基础分析  │
    │ 管理模块  │    │ 管理模块  │    │ 模块     │
    └──────────┘    └──────────┘    └──────────┘
```

---

## 附录：常用命令速查

### PostgreSQL 管理

```bash
# 查看所有数据库
\l

# 切换数据库
\c opinion_system

# 查看所有表
\dt

# 查看表结构
\d projects

# 备份数据库
pg_dump -U opinion_admin opinion_system > backup.sql

# 恢复数据库
psql -U opinion_admin opinion_system < backup.sql
```

### Docker 管理

```bash
# 查看容器状态
docker ps

# 进入容器
docker exec -it opinion_postgres psql -U opinion_admin -d opinion_system

# 停止/启动
docker-compose stop
docker-compose start

# 查看日志
docker-compose logs -f
```

