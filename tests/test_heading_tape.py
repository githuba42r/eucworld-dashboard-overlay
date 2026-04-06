from PIL import Image, ImageDraw, ImageFont

from gopro_overlay.widgets.heading_tape import HeadingTape


font = ImageFont.load_default()


def make_tape(reading, **kwargs):
    defaults = dict(width=400, height=60, reading=reading, font=font)
    defaults.update(kwargs)
    return HeadingTape(**defaults)


def draw_tape(tape):
    img = Image.new("RGBA", (tape.width, tape.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tape.draw(img, draw)
    return img


def has_non_transparent_pixels(img):
    return any(px[3] > 0 for px in img.getdata())


def test_construction_defaults():
    tape = make_tape(lambda: 90.0)
    assert tape.width == 400
    assert tape.height == 60
    assert tape.visible_range == 90
    assert tape.label_interval == 30
    assert tape.tick_interval == 10
    assert tape.show_values is True


def test_visible_range_clamped_to_minimum():
    tape = make_tape(lambda: 0.0, visible_range=5)
    assert tape.visible_range == 10


def test_draw_with_valid_heading():
    tape = make_tape(lambda: 90.0)
    img = draw_tape(tape)
    assert img.size == (400, 60)
    assert has_non_transparent_pixels(img)


def test_draw_heading_north_zero():
    tape = make_tape(lambda: 0.0)
    img = draw_tape(tape)
    assert img.size == (400, 60)
    assert has_non_transparent_pixels(img)


def test_draw_heading_360_wraps_to_0():
    tape = make_tape(lambda: 360.0)
    img = draw_tape(tape)
    assert img.size == (400, 60)
    assert has_non_transparent_pixels(img)


def test_draw_heading_negative_wraps():
    tape = make_tape(lambda: -10.0)
    img = draw_tape(tape)
    assert img.size == (400, 60)
    assert has_non_transparent_pixels(img)


def test_draw_none_heading_shows_placeholder():
    tape = make_tape(lambda: None)
    img = draw_tape(tape)
    assert img.size == (400, 60)
    assert has_non_transparent_pixels(img)


def test_caching_same_heading_reuses_image():
    tape = make_tape(lambda: 90.0)
    draw_tape(tape)
    img1 = tape.image
    draw_tape(tape)
    img2 = tape.image
    assert img1 is img2


def test_caching_different_heading_rebuilds():
    heading = [90.0]
    tape = make_tape(lambda: heading[0])
    draw_tape(tape)
    img1 = tape.image

    heading[0] = 180.0
    draw_tape(tape)
    img2 = tape.image
    assert img1 is not img2


def test_caching_none_to_value_rebuilds():
    heading = [None]
    tape = make_tape(lambda: heading[0])
    draw_tape(tape)
    img1 = tape.image

    heading[0] = 90.0
    draw_tape(tape)
    img2 = tape.image
    assert img1 is not img2


def test_caching_value_to_none_rebuilds():
    heading = [90.0]
    tape = make_tape(lambda: heading[0])
    draw_tape(tape)
    img1 = tape.image

    heading[0] = None
    draw_tape(tape)
    img2 = tape.image
    assert img1 is not img2


def test_custom_colours():
    tape = make_tape(
        lambda: 45.0,
        bg=(10, 20, 30),
        fg=(200, 200, 200),
        marker_rgb=(0, 255, 0),
    )
    img = draw_tape(tape)
    assert img.size == (400, 60)
    assert has_non_transparent_pixels(img)
