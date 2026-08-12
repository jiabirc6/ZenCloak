from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

SIZE = 1024
TOP = (15, 118, 110)
BOTTOM = (22, 160, 133)


def gradient_color(y: int) -> tuple[int, int, int, int]:
    ratio = y / (SIZE - 1)
    return (
        round(TOP[0] + (BOTTOM[0] - TOP[0]) * ratio),
        round(TOP[1] + (BOTTOM[1] - TOP[1]) * ratio),
        round(TOP[2] + (BOTTOM[2] - TOP[2]) * ratio),
        255,
    )


image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
for y in range(SIZE):
    draw.line([(0, y), (SIZE, y)], fill=gradient_color(y))

mask = Image.new("L", (SIZE, SIZE), 0)
mask_draw = ImageDraw.Draw(mask)
mask_draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=210, fill=255)
image.putalpha(mask)

font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 640)
draw = ImageDraw.Draw(image)
draw.text((SIZE / 2, SIZE / 2 - 8), "Z", font=font, fill="white", anchor="mm")

image.save(ASSETS / "zencloak-icon.png")
image.save(
    ASSETS / "zencloak-icon.ico",
    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("ICON_OK", ASSETS / "zencloak-icon.ico")
