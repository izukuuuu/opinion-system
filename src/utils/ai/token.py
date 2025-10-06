# -*- coding: utf-8 -*-
"""
Token counting utilities for Qwen models
"""

from dashscope import get_tokenizer


def count_qwen_tokens(prompt: str, model: str = "qwen-plus") -> int:
    """
    返回 prompt 被 qwen 词表切分后的 token 数量
    支持模型名: qwen-turbo / qwen-plus / qwen-max 等
    
    Args:
        prompt (str): 输入文本
        model (str): 模型名称，默认为 "qwen-turbo"
    
    Returns:
        int: token 数量
    """
    tok = get_tokenizer(model)      # 获取官方 tokenizer
    return len(tok.encode(prompt))


def count_input_tokens(system_prompt: str, user_query: str, model: str = "qwen-plus") -> int:
    """
    计算输入 token 数量（包含 system 和 user 消息）
    
    Args:
        system_prompt (str): 系统提示词
        user_query (str): 用户查询
        model (str): 模型名称，默认为 "qwen-turbo"
    
    Returns:
        int: 输入 token 数量
    """
    # 构造真正发到模型的多轮格式
    full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n" \
                  f"<|im_start|>user\n{user_query}<|im_end|>\n" \
                  f"<|im_start|>assistant\n"
    
    return count_qwen_tokens(full_prompt, model)


def count_output_tokens(assistant_reply: str, model: str = "qwen-plus") -> int:
    """
    计算输出 token 数量（助手回复）
    
    Args:
        assistant_reply (str): 助手回复内容
        model (str): 模型名称，默认为 "qwen-turbo"
    
    Returns:
        int: 输出 token 数量
    """
    return count_qwen_tokens(assistant_reply, model)


def count_total_tokens(system_prompt: str, user_query: str, assistant_reply: str, model: str = "qwen-plus") -> dict:
    """
    计算总 token 数量（输入 + 输出）
    
    Args:
        system_prompt (str): 系统提示词
        user_query (str): 用户查询
        assistant_reply (str): 助手回复
        model (str): 模型名称，默认为 "qwen-turbo"
    
    Returns:
        dict: 包含输入、输出和总 token 数量的字典
    """
    input_tokens = count_input_tokens(system_prompt, user_query, model)
    output_tokens = count_output_tokens(assistant_reply, model)
    total_tokens = input_tokens + output_tokens
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens
    }
