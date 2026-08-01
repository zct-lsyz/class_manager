from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """从字典按 key 取值"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def split(value, separator=","):
    """将字符串按分隔符拆分为列表（如步骤指示器的 labels）"""
    if value is None:
        return []
    return [part for part in str(value).split(separator)]
