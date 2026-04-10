"""生成半透明贴纸 PNG 素材"""
import math
import random
from PIL import Image, ImageDraw

STICKER_DIR = "data/stickers"
SIZE = 200  # 基准尺寸，合成时按视频分辨率缩放


def draw_circle(path):
    """半透明彩色圆形"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (random.randint(100, 255), random.randint(100, 255), random.randint(50, 200), random.randint(100, 180))
    draw.ellipse([10, 10, SIZE - 10, SIZE - 10], fill=color, outline=(255, 255, 255, 120), width=3)
    img.save(path)


def draw_star(path):
    """半透明五角星"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy, r = SIZE // 2, SIZE // 2, SIZE // 2 - 10
    points = []
    for i in range(10):
        angle = math.radians(i * 36 - 90)
        radius = r if i % 2 == 0 else r * 0.4
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    color = (random.randint(200, 255), random.randint(150, 255), random.randint(0, 100), random.randint(100, 170))
    draw.polygon(points, fill=color, outline=(255, 255, 255, 140), width=2)
    img.save(path)


def draw_heart(path):
    """半透明心形"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (random.randint(200, 255), random.randint(50, 120), random.randint(80, 150), random.randint(100, 170))
    # 用两个圆+三角形近似心形
    r = SIZE // 4
    cx, cy = SIZE // 2, SIZE // 2
    draw.ellipse([cx - r * 2, cy - r, cx, cy + r], fill=color)
    draw.ellipse([cx, cy - r, cx + r * 2, cy + r], fill=color)
    draw.polygon([(cx - r * 2, cy), (cx + r * 2, cy), (cx, cy + r * 2)], fill=color)
    img.save(path)


def draw_diamond(path):
    """半透明菱形"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    r = SIZE // 2 - 15
    points = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    color = (random.randint(50, 200), random.randint(150, 255), random.randint(200, 255), random.randint(100, 170))
    draw.polygon(points, fill=color, outline=(255, 255, 255, 130), width=3)
    img.save(path)


def draw_rounded_rect(path):
    """半透明圆角矩形"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (random.randint(100, 230), random.randint(100, 230), random.randint(100, 230), random.randint(90, 160))
    draw.rounded_rectangle([15, 15, SIZE - 15, SIZE - 15], radius=25, fill=color, outline=(255, 255, 255, 120), width=3)
    img.save(path)


def draw_triangle(path):
    """半透明三角形"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 15
    points = [(SIZE // 2, margin), (SIZE - margin, SIZE - margin), (margin, SIZE - margin)]
    color = (random.randint(50, 200), random.randint(200, 255), random.randint(100, 200), random.randint(100, 160))
    draw.polygon(points, fill=color, outline=(255, 255, 255, 130), width=3)
    img.save(path)


def draw_ring(path):
    """半透明圆环"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (random.randint(150, 255), random.randint(80, 200), random.randint(50, 255), random.randint(120, 180))
    draw.ellipse([10, 10, SIZE - 10, SIZE - 10], outline=color, width=12)
    img.save(path)


def draw_cross(path):
    """半透明十字形"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (random.randint(200, 255), random.randint(100, 255), random.randint(50, 150), random.randint(100, 170))
    arm = SIZE // 5
    cx, cy = SIZE // 2, SIZE // 2
    r = SIZE // 2 - 15
    draw.rounded_rectangle([cx - arm, cy - r, cx + arm, cy + r], radius=10, fill=color)
    draw.rounded_rectangle([cx - r, cy - arm, cx + r, cy + arm], radius=10, fill=color)
    img.save(path)


if __name__ == "__main__":
    generators = [
        ("circle", draw_circle),
        ("star", draw_star),
        ("heart", draw_heart),
        ("diamond", draw_diamond),
        ("rounded_rect", draw_rounded_rect),
        ("triangle", draw_triangle),
        ("ring", draw_ring),
        ("cross", draw_cross),
    ]
    for name, func in generators:
        path = f"{STICKER_DIR}/{name}.png"
        func(path)
        print(f"  生成: {path}")
    print(f"\n共生成 {len(generators)} 个贴纸")
