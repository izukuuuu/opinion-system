"""LangGraph Studio 开发服务器启动脚本

启动方式：
    uv run --no-sync python backend/langgraph_server.py

访问地址：
    http://127.0.0.1:2024

LangSmith Studio 连接：
    https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
"""
import os
import sys
from pathlib import Path

# 设置 UTF-8 输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 设置工作目录为 backend
backend_dir = Path(__file__).parent
os.chdir(backend_dir)

# 确保环境变量已加载
from dotenv import load_dotenv
env_path = backend_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[OK] Loaded env: {env_path}")

# 检查必需的 API Key
langsmith_key = os.getenv("LANGSMITH_API_KEY")
if langsmith_key:
    print(f"[OK] LANGSMITH_API_KEY: ...{langsmith_key[-8:]}")
else:
    print("[WARN] LANGSMITH_API_KEY not configured")

# 启动 LangGraph 开发服务器
import subprocess

if __name__ == "__main__":
    print("\n" + "="*60)
    print("LangGraph Studio Dev Server")
    print("="*60)
    print(f"Working dir: {backend_dir}")
    print(f"Config: {backend_dir / 'langgraph.json'}")
    print("\nStarting server (auto-detect port)...")
    print("="*60 + "\n")

    # 使用 subprocess 调用 langgraph dev (自动分配端口)
    try:
        subprocess.run(
            ["langgraph", "dev"],
            cwd=backend_dir,
            check=True
        )
    except KeyboardInterrupt:
        print("\nServer stopped")
    except subprocess.CalledProcessError as e:
        print(f"\nError: {e}")
        sys.exit(1)
