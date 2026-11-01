"""生成机器人头像：一只圆滚滚的大肥鱼，1024x1024 PNG。

用法：python scripts/make_avatar.py
产物：assets/avatar.png
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "avatar.png"

SIZE = 1024
SS = 4
W = SIZE * SS

BG = (247, 239, 228)
DISC = (241, 224, 202)
BODY_TOP = (250, 143, 108)
BODY_BOT = (230, 96, 70)
FIN = (236, 104, 76)
BELLY = (255, 218, 194)
EYE = (40, 37, 47)
BLUSH = (255, 132, 120)

U = W * 0.26                      # 1 单位 = 0.26 画布宽
OX = W * 0.5 + 0.30 * U           # 让整条鱼（含尾巴）视觉居中
OY = W * 0.52


def P(x: float, y: float) -> tuple[float, float]:
    return (OX + x * U, OY + y * U)


def cubic(p0, p1, p2, p3, n: int = 48):
    pts = []
    for i in range(n):
        t = i / (n - 1)
        m = 1 - t
        x = m**3 * p0[0] + 3 * m**2 * t * p1[0] + 3 * m * t**2 * p2[0] + t**3 * p3[0]
        y = m**3 * p0[1] + 3 * m**2 * t * p1[1] + 3 * m * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def outline(segments, n: int = 48):
    pts = []
    for seg in segments:
        pts.extend(cubic(*seg, n=n)[:-1])
    return pts


def add(base: Image.Image, paint, blur: float = 0.0) -> Image.Image:
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer))
    if blur:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(base, layer)


# 鱼身：鼻子在右，尾巴在左
BODY = outline(
    [
        (P(1.02, 0.0), P(0.98, 0.40), P(0.58, 0.62), P(0.10, 0.63)),
        (P(0.10, 0.63), P(-0.32, 0.63), P(-0.72, 0.42), P(-0.94, 0.17)),
        (P(-0.94, 0.17), P(-0.98, -0.16), P(-0.62, -0.58), P(-0.12, -0.66)),
        (P(-0.12, -0.66), P(0.38, -0.73), P(0.92, -0.50), P(1.02, 0.0)),
    ]
)

TAIL = outline(
    [
        (P(-0.84, 0.20), P(-1.10, 0.34), P(-1.38, 0.50), P(-1.62, 0.52)),
        (P(-1.62, 0.52), P(-1.48, 0.28), P(-1.30, 0.10), P(-1.20, 0.0)),
        (P(-1.20, 0.0), P(-1.34, -0.16), P(-1.50, -0.36), P(-1.62, -0.52)),
        (P(-1.62, -0.52), P(-1.36, -0.50), P(-1.08, -0.34), P(-0.84, -0.20)),
    ]
)

DORSAL = outline(
    [
        (P(-0.62, 0.40), P(-0.58, 0.66), P(-0.44, 0.78), P(-0.30, 0.78)),
        (P(-0.30, 0.78), P(-0.20, 0.66), P(-0.06, 0.60), P(0.02, 0.57)),
    ]
)

PELVIC = outline(
    [
        (P(-0.16, -0.62), P(-0.22, -0.80), P(-0.34, -0.88), P(-0.44, -0.86)),
        (P(-0.44, -0.86), P(-0.40, -0.72), P(-0.34, -0.66), P(-0.30, -0.62)),
    ]
)

# 胸鳍：一片小叶子的形状
PECTORAL = outline(
    [
        (P(0.02, 0.02), P(-0.10, 0.10), P(-0.24, 0.02), P(-0.26, -0.12)),
        (P(-0.26, -0.12), P(-0.16, -0.10), P(-0.02, -0.10), P(0.02, 0.02)),
    ]
)


def disc_mask() -> Image.Image:
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).ellipse([OX - 1.02 * U, OY - 1.02 * U, OX + 1.02 * U, OY + 1.02 * U], fill=255)
    return mask


img = Image.new("RGB", (W, W), BG).convert("RGBA")

# 背景的浅色圆，给构图一个底
img = add(
    img,
    lambda d: d.ellipse(
        [OX - 1.06 * U, OY - 1.06 * U, OX + 1.06 * U, OY + 1.06 * U], fill=(*DISC, 255)
    ),
)

# 水里的影子
img = add(
    img,
    lambda d: d.ellipse(
        [OX - 0.85 * U, OY + 0.52 * U, OX + 0.85 * U, OY + 0.78 * U], fill=(120, 80, 60, 46)
    ),
    blur=W * 0.02,
)

# 尾巴、背鳍、臀鳍先画，根部会被身体压住
img = add(img, lambda d: d.polygon(TAIL, fill=(*FIN, 255)))
img = add(img, lambda d: d.polygon(DORSAL, fill=(*FIN, 255)))
img = add(img, lambda d: d.polygon(PELVIC, fill=(*FIN, 245)))

# 身体：竖直渐变填进轮廓
body_layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
bmask = Image.new("L", (W, W), 0)
ImageDraw.Draw(bmask).polygon(BODY, fill=255)
grad = Image.new("RGB", (W, W), BODY_TOP)
gd = ImageDraw.Draw(grad)
for y in range(W):
    t = min(1.0, max(0.0, (y / W - 0.28) / 0.48))
    gd.line(
        [(0, y), (W, y)],
        fill=tuple(round(BODY_TOP[i] + (BODY_BOT[i] - BODY_TOP[i]) * t) for i in range(3)),
    )
body_layer.paste(grad, (0, 0), bmask)
img = Image.alpha_composite(img, body_layer)

# 肚子：贴身的浅色
img = add(
    img,
    lambda d: d.ellipse(
        [OX - 0.62 * U, OY + 0.06 * U, OX + 0.86 * U, OY + 0.92 * U], fill=(*BELLY, 150)
    ),
    blur=W * 0.03,
)

# 胸鳍
img = add(img, lambda d: d.polygon(PECTORAL, fill=(*FIN, 210)))

# 头顶点高光
img = add(
    img,
    lambda d: d.ellipse(
        [OX - 0.20 * U, OY - 0.50 * U, OX + 0.52 * U, OY - 0.06 * U], fill=(255, 255, 255, 40)
    ),
    blur=W * 0.04,
)

# 眼睛
ex, ey = P(0.50, 0.06)
er = 0.155 * U
img = add(img, lambda d: d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=(*EYE, 255)))
img = add(
    img,
    lambda d: d.ellipse(
        [ex - er * 0.45, ey - er * 0.55, ex - er * 0.02, ey - er * 0.10],
        fill=(255, 255, 255, 245),
    ),
)
img = add(
    img,
    lambda d: d.ellipse(
        [ex + er * 0.10, ey + er * 0.22, ex + er * 0.40, ey + er * 0.52],
        fill=(255, 255, 255, 165),
    ),
)

# 腮红
bx, by = P(0.52, -0.30)
img = add(
    img,
    lambda d: d.ellipse(
        [bx - 0.20 * U, by - 0.09 * U, bx + 0.20 * U, by + 0.09 * U], fill=(*BLUSH, 105)
    ),
    blur=W * 0.022,
)

# 嘴：一个小小的笑
mx, my = P(0.86, -0.06)
img = add(
    img,
    lambda d: d.arc(
        [mx - 0.075 * U, my - 0.05 * U, mx + 0.075 * U, my + 0.07 * U],
        start=18, end=145, fill=(150, 56, 40, 255), width=int(W * 0.006),
    ),
)

# 小气泡
for cx_, cy_, r_ in ((1.30, 0.28, 0.045), (1.44, 0.10, 0.030), (1.22, 0.44, 0.020)):
    bx_, by_ = P(cx_, cy_)
    rr = r_ * U
    img = add(
        img,
        lambda d, bx_=bx_, by_=by_, rr=rr: d.ellipse(
            [bx_ - rr, by_ - rr, bx_ + rr, by_ + rr], fill=(255, 255, 255, 120)
        ),
    )
    img = add(
        img,
        lambda d, bx_=bx_, by_=by_, rr=rr: d.arc(
            [bx_ - rr, by_ - rr, bx_ + rr, by_ + rr],
            start=150, end=330, fill=(255, 255, 255, 190), width=int(W * 0.004),
        ),
    )

# ---------------------------------------------------------------- 输出
img = img.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)

# 极轻的低频颗粒，去掉塑料感又不撑大文件
small = np.random.default_rng(11).normal(0, 1.0, (48, 48))
texture = Image.fromarray(((small - small.min()) / np.ptp(small) * 255).astype(np.uint8), "L")
texture = texture.resize((SIZE, SIZE), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))
tex = (np.asarray(texture, dtype=np.float32) - 128.0) * 0.05
arr = np.clip(np.asarray(img, dtype=np.float32) + tex[..., None], 0, 255).astype(np.uint8)
img = Image.fromarray(arr, "RGB")

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, "PNG", optimize=True)
print(f"saved: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
