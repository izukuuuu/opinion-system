# 数据清洗模块使用说明

本文档说明 `backend/src/clean` 模块中各函数的职责以及如何调用清洗流水线。

## 模块结构

- `__init__.py`：导出 `run_clean` 供外部模块直接调用。
- `data_clean.py`：实现全部清洗逻辑，包括时间解析、文本处理、地域标准化与流水线调度。

## 核心函数

### `parse_datetime(time_str: str, formats: List[str] = None) -> Optional[datetime]`

- 解析多种格式的时间字符串，优先按指定格式尝试，失败时回退到 `dateutil` 的自动解析能力。
- 所有解析成功的时间统一设置为上海时区，并转换为 `datetime` 对象，失败返回 `None`。

### `clean_text_whitespace(text: str) -> str`

- 保留原始标点，仅折叠多余空白字符并去除首尾空白。
- 缺失值会被转换为空字符串，确保后续字符串拼接安全。

### `normalize_region(region: str, fillna: str = "未知") -> str`

- 将地域字段标准化为省级称呼，并在缺失时使用配置的默认值填充。
- 内置常见省份与自治区的映射，可保证输出稳定。

### `run_clean(topic: str, date: str, logger=None) -> bool`

数据清洗主流程，步骤包括：

1. 遍历 `data/merge/<topic>/<date>` 下的 Excel 文件，每个文件视为一个渠道。
2. 基于渠道配置 (`channels.yaml.field_alias`) 重命名列，保证字段标准化。
3. 对内容字段执行两轮去重：先按 `content`，再按合成的 `contents`。
4. 将 `title`、`summary`、`ocr`、`content` 拼接成带标签的 `contents` 字段，并清理空白字符。
5. 依据配置标准化地域、解析发布时间、补齐平台信息，缺失字段统一填充 "未知"。
6. 为每条记录生成 `yyyymmdd` 前缀的自增整型 `id`，保留关键列并写回 `data/clean/<topic>/<date>/<channel>.xlsx`。

函数返回是否至少成功处理一个渠道文件，可用于判断任务执行结果。

## 调用示例

```python
from backend.src.clean import run_clean

if __name__ == "__main__":
    success = run_clean(topic="示例专题", date="2024-06-01")
    if not success:
        raise SystemExit("清洗失败，请检查日志输出。")
```

调用前请确保：

- `data/merge/<topic>/<date>` 目录已存在并包含需清洗的 Excel 文件。
- `configs/channels.yaml`（或其他渠道配置）提供了字段别名与地域配置。
- `backend/src/utils` 下的日志、路径、Excel I/O 配置均已正确初始化。
