from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """从字典按 key 取值"""
    if dictionary is None:
        return None
    return dictionary.get(key)
