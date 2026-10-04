"""生成 App 图标。

Apple 要求 1024x1024 满幅方形（系统自己加圆角遮罩），所以脚本不做圆角。
用 4 倍超采样再缩放，避免圆角矩形和多边形边缘出现锯齿。

    python tools/make_icon.py            # 写入 LifeAssistant/Assets.xcassets

改配色只需改 TOP / BOTTOM 两个常量后重跑。
"""

from __future__ import annotations

import pathlib

import numpy as np
from PIL import Image, ImageDraw

TOP = (196, 85, 42)      # #C4552A 暖陶土
BOTTOM = (142, 52, 19)   # #8E3413
CARD = (255, 252, 248)   # 纸张白

SIZE = 1024
SS = 4                   # 超采样倍数
W = SIZE * SS

OUT = pathlib.Path(__file__).resolve().parents[1] / "LifeAssistant" / "Assets.xcassets" / "AppIcon.appiconset"


def gradient(size: int) -> Image.Image:
    """左上到右下的线性渐变底。"""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    t = np.clip((x + y) / (2.0 * (size - 1)), 0.0, 1.0)[..., None]
    top = np.array(TOP, dtype=np.float32)
    bottom = np.array(BOTTOM, dtype=np.float32)
    rgb = (top * (1.0 - t) + bottom * t).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def build() -> Image.Image:
    img = gradient(W).convert("RGBA")

    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    white = (*CARD, 255)
    clay = (*TOP, 255)

    def s(*points: float) -> list[tuple[float, float]]:
        return [(p * SS, q * SS) for p, q in zip(points[::2], points[1::2])]

    # 对话气泡
    d.rounded_rectangle(
        (212 * SS, 286 * SS, 812 * SS, 704 * SS),
        radius=98 * SS,
        fill=white,
    )
    # 气泡尾巴
    d.polygon(s(336, 676, 288, 796, 462, 700), fill=white)

    # 气泡内的定位针
    cx, cy, r = 512, 462, 102
    d.ellipse(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), fill=clay)
    d.polygon(s(cx - 86, cy + 40, cx, cy + 238, cx + 86, cy + 40), fill=clay)
    # 针孔
    hr = 40
    d.ellipse(((cx - hr) * SS, (cy - hr) * SS, (cx + hr) * SS, (cy + hr) * SS), fill=white)

    img.alpha_composite(layer)
    return img.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon = build()
    target = OUT / "AppIcon-1024.png"
    icon.save(target, "PNG", optimize=True)
    print(f"written: {target}  {icon.size[0]}x{icon.size[1]}  {target.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
