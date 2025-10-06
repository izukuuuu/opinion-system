"""
环境变量加载工具
确保.env文件被正确加载到系统环境变量中
"""

import os
from pathlib import Path
from typing import Optional
# 避免循环导入，在函数内部导入

def load_env_file(env_file_path: Optional[str] = None) -> bool:
    """
    加载.env文件到环境变量
    
    Args:
        env_file_path (Optional[str]): .env文件路径，如果为None则自动查找
    
    Returns:
        bool: 是否成功加载
    """
    if env_file_path is None:
        # 自动查找.env文件
        current_dir = Path.cwd()
        env_file_path = current_dir / '.env'
        
        # 如果当前目录没有，向上查找
        if not env_file_path.exists():
            for parent in current_dir.parents:
                potential_env = parent / '.env'
                if potential_env.exists():
                    env_file_path = potential_env
                    break
    
    if not env_file_path or not Path(env_file_path).exists():
        return False
    
    try:
        with open(env_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                
                # 解析键值对
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引号
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # 设置环境变量
                    if key and value != 'your_qwen_api_key_here':
                        os.environ[key] = value
        
        return True
        
    except Exception:
        return False

def get_api_key() -> Optional[str]:
    """
    获取千问API密钥
    
    Returns:
        Optional[str]: API密钥，如果未配置则返回None
    """
    # 首先尝试从环境变量获取
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    
    if api_key and api_key != 'your_qwen_api_key_here':
        return api_key
    
    # 如果环境变量中没有，尝试加载.env文件
    if load_env_file():
        api_key = os.environ.get('DASHSCOPE_API_KEY')
        if api_key and api_key != 'your_qwen_api_key_here':
            return api_key
    
    return None

def validate_api_key() -> bool:
    """
    验证千问API密钥是否有效
    
    Returns:
        bool: 是否有效
    """
    api_key = get_api_key()
    
    if not api_key:
        return False
    
    if api_key == 'your_qwen_api_key_here':
        return False
    
    return True

