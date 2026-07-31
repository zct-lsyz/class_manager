import io
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_HYGIENE_PHOTO_SIZE = 3 * 1024 * 1024


def prepare_hygiene_photo(uploaded):
    """校验图片，并在需要时压缩到 3MB 以内。"""
    original_size = uploaded.size
    try:
        image = ImageOps.exif_transpose(Image.open(uploaded))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(f"{uploaded.name} 不是可识别的图片。") from exc

    if original_size <= MAX_HYGIENE_PHOTO_SIZE:
        uploaded.seek(0)
        return ContentFile(uploaded.read(), name=Path(uploaded.name).name), original_size

    if image.mode not in ("RGB", "L"):
        background = Image.new("RGB", image.size, "white")
        if "A" in image.getbands():
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image)
        image = background
    elif image.mode == "L":
        image = image.convert("RGB")

    image.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
    data = b""
    for quality in (88, 82, 76, 70, 64, 58, 52, 46, 40):
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        data = output.getvalue()
        if len(data) <= MAX_HYGIENE_PHOTO_SIZE:
            break
    while len(data) > MAX_HYGIENE_PHOTO_SIZE and max(image.size) > 1200:
        image.thumbnail((int(image.width * 0.82), int(image.height * 0.82)), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=60, optimize=True)
        data = output.getvalue()
    if len(data) > MAX_HYGIENE_PHOTO_SIZE:
        raise ValidationError(f"{uploaded.name} 压缩后仍超过 3MB，请先缩小图片尺寸。")
    return ContentFile(data, name=f"{Path(uploaded.name).stem}.jpg"), original_size
