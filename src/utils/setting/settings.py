"""
项目配置管理模块
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, List
from .paths import get_configs_root, get_project_root


class Settings:
    """项目配置管理类"""
    
    def __init__(self, logger=None):
        """
        初始化配置管理器
        
        Args:
            logger: 日志记录器
        """
        self.configs = {}
        self._load_configs(logger)
    
    def _load_configs(self, logger=None):
        """
        加载所有配置文件
        
        Args:
            logger: 日志记录器
        """
        # 优先使用环境变量指定的配置目录
        config_dir = get_configs_root()
        
        # 加载YAML配置文件
        yaml_files = list(config_dir.glob("*.yaml"))
        for config_file in yaml_files:
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.configs[config_file.stem] = yaml.safe_load(f)
            except Exception as e:
                pass
        
        # 加载环境变量配置
        self.configs['env'] = {}
        for key, value in os.environ.items():
            if key.startswith('OPINION_'):
                self.configs['env'][key] = value
        
        # 添加项目路径信息
        project_root = get_project_root()
        self.configs['paths'] = {
            'project_root': str(project_root),
            'configs_dir': str(get_configs_root()),
            'data_dir': str(project_root / 'data'),
            'logs_dir': str(project_root / 'logs'),
            'templates_dir': str(project_root / 'templates')
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持点号分隔的嵌套键
        
        Args:
            key (str): 配置键，支持点号分隔如 'defaults.db_url'
            default (Any): 默认值
        
        Returns:
            Any: 配置值
        """
        keys = key.split('.')
        value = self.configs
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_channel_config(self) -> Dict[str, Any]:
        """
        获取渠道配置
        
        Returns:
            Dict[str, Any]: 渠道配置
        """
        return self.configs.get('channels', {})
    
    def get_analysis_config(self) -> Dict[str, Any]:
        """
        获取分析配置
        
        Returns:
            Dict[str, Any]: 分析配置
        """
        return self.configs.get('analysis', {})
    
    def get_prompts_config(self) -> Dict[str, Any]:
        """
        获取提示词配置
        
        Returns:
            Dict[str, Any]: 提示词配置
        """
        return self.configs.get('prompts', {})
    
    def get_llm_config(self) -> Dict[str, Any]:
        """
        获取LLM配置
        
        Returns:
            Dict[str, Any]: LLM配置
        """
        return self.configs.get('llm', {})
    
    def get_project_paths(self) -> Dict[str, str]:
        """
        获取项目路径信息
        
        Returns:
            Dict[str, str]: 项目路径字典
        """
        return self.configs.get('paths', {})

# 全局配置实例
settings = Settings()
