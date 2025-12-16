"""
文本处理工具函数
"""


def clean_prefix(text: str) -> str:
    """
    去除重复的前缀，如"描述：描述：描述内容"、"描述描述内容"都只保留一个
    
    Args:
        text: 需要处理的文本
        
    Returns:
        处理后的文本
    """
    prefixes = [
        "描述：", "描述", "名称：", "名称", "资源描述：", "资源描述",
        "简介：", "简介", "剧情简介：", "剧情简介", "内容简介：", "内容简介"
    ]
    text = text.strip()
    for prefix in prefixes:
        while text.startswith(prefix):
            text = text[len(prefix):].lstrip()
    return text

