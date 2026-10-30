import pytest
from PIL import Image, ImageDraw

from tools.scripts.atlas import frames


def test_odd_bounds() -> None:
    with Image.new("RGBA", (513, 377)) as image:
        draw = ImageDraw.Draw(image)
        original = [(x, y, x + 70, y + 90) for y in (25, 220) for x in (10, 140, 270, 400)]
        for rectangle in original:
            draw.rectangle(rectangle, fill=(50, 80, 100, 255))
        boxes = frames(image)
        assert len(boxes) == 8
        for (left, top, right, bottom), (x, y, width, height) in zip(original, boxes, strict=True):
            assert x <= left < right <= x + width <= image.width
            assert y <= top < bottom <= y + height <= image.height
        draw.rectangle((12, 3, 15, 6), fill=(255, 0, 0, 2))
        assert frames(image) == boxes
        draw.rectangle((210, 130, 260, 190), fill=(255, 0, 0, 255))
        with pytest.raises(ValueError, match="found 9"):
            frames(image)


def test_runtime_bounds() -> None:
    import tomllib

    from tools.scripts.atlas import ASSETS

    data = tomllib.loads((ASSETS / "cartoons/index.toml").read_text())["species"]
    assert len(data) == 51
    for name, atlas in data.items():
        path = ASSETS / (f"{name}.webp" if name == "guests" else f"cartoons/{name}.webp")
        with Image.open(path) as image:
            assert list(image.size) == atlas["size"], name
            assert image.mode == "RGBA", name
            assert len(atlas["frames"]) in ({8} if name == "guests" else {2, 3})
            for x, y, width, height in atlas["frames"]:
                assert 0 <= x < x + width <= image.width, name
                assert 0 <= y < y + height <= image.height, name


def test_row_order() -> None:
    with Image.new("RGBA", (500, 200)) as image:
        draw = ImageDraw.Draw(image)
        for row in range(2):
            for column in range(5):
                draw.rectangle(
                    (
                        column * 100 + 10,
                        row * 100 + column * 2 + 10,
                        column * 100 + 60,
                        row * 100 + column * 2 + 60,
                    ),
                    fill="white",
                )
        boxes = frames(image, count=10, columns=5)
        assert [x // 100 for x, _, _, _ in boxes] == [0, 1, 2, 3, 4] * 2
