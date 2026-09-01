from __future__ import annotations

WIDTH = 128
HEIGHT = 64


class Framebuffer:
    """1-bit 128×64. SSD1322 is 4-bit greyscale; 1-bit is enough for stage UI in 0.1."""

    __slots__ = ("width", "height", "pixels")

    def __init__(self, width: int = WIDTH, height: int = HEIGHT) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height)

    def clear(self, value: int = 0) -> None:
        fill = 1 if value else 0
        for i in range(len(self.pixels)):
            self.pixels[i] = fill

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y * self.width + x] = 1 if on else 0

    def get(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.pixels[y * self.width + x]
        return 0

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        for i in range(w):
            self.pixel(x + i, y, on)

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        for i in range(h):
            self.pixel(x, y + i, on)

    def fill_rect(self, x: int, y: int, w: int, h: int, on: bool = True) -> None:
        for yy in range(h):
            for xx in range(w):
                self.pixel(x + xx, y + yy, on)

    def invert(self) -> None:
        for i, v in enumerate(self.pixels):
            self.pixels[i] = 0 if v else 1

    def copy_from(self, other: Framebuffer) -> None:
        self.pixels[:] = other.pixels

    def digest(self) -> bytes:
        return bytes(self.pixels)

    def to_ascii(self, on: str = "#", off: str = ".") -> str:
        rows = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                row.append(on if self.get(x, y) else off)
            rows.append("".join(row))
        return "\n".join(rows)

    def to_ppm(self, scale: int = 4, on_rgb: tuple[int, int, int] = (220, 230, 180)) -> bytes:
        w, h = self.width * scale, self.height * scale
        header = f"P6\n{w} {h}\n255\n".encode()
        body = bytearray()
        off = (8, 10, 8)
        for y in range(self.height):
            for _sy in range(scale):
                for x in range(self.width):
                    color = on_rgb if self.get(x, y) else off
                    body.extend(bytes(color) * scale)
        return header + bytes(body)
