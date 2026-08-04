"""宿舍分配服务。"""


def release_bed(bed):
    """释放床位：清除所有分配（含历史 is_current=False）对该床的引用。

    DormAssignment.bed 是 OneToOneField，bed_id 有全局唯一约束；历史分配若仍引用该床，
    会阻止新分配复用同一张床。分配/改床/导入前必须先释放。
    """
    from apps.dormitory.models import DormAssignment
    DormAssignment.objects.filter(bed=bed).update(bed=None)


def first_free_bed(room):
    """返回宿舍第一张空闲床（未被当前分配占用），无空闲则 None。"""
    from apps.dormitory.models import DormAssignment, DormBed
    occupied = set(DormAssignment.objects.filter(
        room=room, is_current=True, bed__isnull=False,
    ).values_list("bed_id", flat=True))
    for b in DormBed.objects.filter(room=room, is_active=True).order_by("bed_number"):
        if b.id not in occupied:
            return b
    return None
