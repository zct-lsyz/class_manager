# -*- coding: utf-8 -*-
"""生成 PWA 图标：蓝色渐变底 + 白色帽徽。仅需 Pillow。"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def generate(size, path):
    # 渐变底色
    img = Image.new("RGB", (size, size))
    top = (26, 115, 232)    # #1a73e8
    bottom = (21, 87, 176)  # #1557b0
    for y in range(size):
        ratio = y / size
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(size):
            img.putpixel((x, y), color)

    draw = ImageDraw.Draw(img)
    # 白色帽徽
    margin = size * 0.18
    draw.polygon(
        [
            (size * 0.5, size * 0.22),
            (size * 0.18, size * 0.36),
            (size * 0.5, size * 0.50),
            (size * 0.82, size * 0.36),
        ],
        fill="white",
    )
    # 帽沿
    draw.rounded_rectangle(
        [size * 0.18, size * 0.50, size * 0.82, size * 0.58],
        radius=size * 0.02,
        fill="white",
    )
    # 帽流苏
    draw.line([(size * 0.5, size * 0.5), (size * 0.5, size * 0.68)], fill="white", width=max(2, size // 60))
    draw.polygon(
        [
            (size * 0.5, size * 0.68),
            (size * 0.44, size * 0.82),
            (size * 0.56, size * 0.82),
        ],
        fill="white",
    )
    img.save(path, "PNG")
    print(f"Generated {path} ({size}x{size})")


if __name__ == "__main__":
    generate(192, os.path.join(OUT_DIR, "icon-192.png"))
    generate(512, os.path.join(OUT_DIR, "icon-512.png"))
