from django import template


register = template.Library()


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return None
    return mapping.get(key)


@register.filter
def split(value, separator=","):
    """将字符串按分隔符拆分为列表（如步骤指示器的 labels）"""
    if value is None:
        return []
    return [part for part in str(value).split(separator)]
