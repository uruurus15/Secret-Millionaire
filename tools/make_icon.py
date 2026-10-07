"""アプリのアイコン（傾いたトランプに「？」）を生成する

  python tools/make_icon.py   → web/icon.ico（exe・ウィンドウ・ブラウザのタブ共通）と web/icon.png
Pillow が必要: pip install pillow
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT_ICO = os.path.join(ROOT, 'web', 'icon.ico')
OUT_PNG = os.path.join(ROOT, 'web', 'icon.png')

S = 1024                 # 作業キャンバス（最後に縮小してなめらかにする）
CARD_W, CARD_H = 560, 800
RADIUS = 64
TILT = -14               # 時計回りに傾ける
RED = (212, 42, 58, 255)
DARK_RED = (120, 12, 24, 255)
GOLD = (214, 166, 48, 255)
INK = (40, 40, 44, 255)


def font(size):
    for name in ('ariblk.ttf', 'seguibl.ttf', 'arialbd.ttf'):
        path = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def centered_text(draw, cx, cy, text, fnt, fill, stroke=0, stroke_fill=None):
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt, stroke_width=stroke)
    draw.text((cx - (l + r) / 2, cy - (t + b) / 2), text, font=fnt, fill=fill,
              stroke_width=stroke, stroke_fill=stroke_fill)


def make_card():
    pad = 40
    card = Image.new('RGBA', (CARD_W + pad * 2, CARD_H + pad * 2), (0, 0, 0, 0))
    # 白からクリーム色へのグラデーション
    grad = Image.new('RGBA', (CARD_W, CARD_H))
    gd = ImageDraw.Draw(grad)
    for y in range(CARD_H):
        k = y / CARD_H
        gd.line([(0, y), (CARD_W, y)], fill=(255, int(255 - 14 * k), int(250 - 40 * k), 255))
    mask = Image.new('L', (CARD_W, CARD_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], RADIUS, fill=255)
    card.paste(grad, (pad, pad), mask)

    d = ImageDraw.Draw(card)
    x0, y0, x1, y1 = pad, pad, pad + CARD_W - 1, pad + CARD_H - 1
    d.rounded_rectangle([x0, y0, x1, y1], RADIUS, outline=INK, width=14)            # 外枠
    inset = 46
    d.rounded_rectangle([x0 + inset, y0 + inset, x1 - inset, y1 - inset], RADIUS - 30,
                        outline=GOLD, width=10)                                     # 金の内枠

    cx, cy = pad + CARD_W / 2, pad + CARD_H / 2
    centered_text(d, cx, cy + 10, '?', font(600), RED, stroke=14, stroke_fill=DARK_RED)  # 中央の大きな「？」

    # 角の小さな「？」（右下は上下逆さ）
    corner = Image.new('RGBA', (140, 150), (0, 0, 0, 0))
    centered_text(ImageDraw.Draw(corner), 70, 75, '?', font(120), RED)
    card.alpha_composite(corner, (int(x0 + 20), int(y0 + 18)))
    card.alpha_composite(corner.rotate(180), (int(x1 - 20 - 140), int(y1 - 18 - 150)))
    return card


def main():
    card = make_card().rotate(TILT, resample=Image.BICUBIC, expand=True)
    canvas = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ox, oy = (S - card.width) // 2, (S - card.height) // 2

    # 影
    alpha = card.split()[3].point(lambda a: int(a * 0.45))
    shadow = Image.new('RGBA', card.size, (0, 0, 0, 255))
    shadow.putalpha(alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.alpha_composite(shadow, (ox + 18, oy + 24))
    canvas.alpha_composite(card, (ox, oy))

    icon = canvas.resize((256, 256), Image.LANCZOS)
    icon.save(OUT_PNG)
    icon.save(OUT_ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print('saved', OUT_ICO, OUT_PNG)


if __name__ == '__main__':
    main()
