"""学生相关服务。"""


def build_student_options(queryset):
    """构建学生选项列表（含床位号），供前端「选择学生」复选框组件使用。

    返回 [{id, name, bed}]，bed 为空串表示未分配床位。
    """
    return [
        {"id": s.pk, "name": s.name, "bed": s.display_bed_number}
        for s in queryset
    ]
