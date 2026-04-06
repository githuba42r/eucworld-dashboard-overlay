import random
from datetime import timedelta

import pytest

from gopro_overlay import fake
from gopro_overlay.layout_xml import layout_from_xml, Converters
from gopro_overlay.privacy import NoPrivacyZone
from PIL import ImageFont

rng = random.Random()
rng.seed(12345)

framemeta = fake.fake_framemeta(length=timedelta(minutes=1), step=timedelta(seconds=1), rng=rng)
font = ImageFont.load_default()


def parse_xml(xml):
    """Parse and invoke the XML layout factory."""
    from gopro_overlay.entry import Entry
    from datetime import datetime, timezone
    factory = layout_from_xml(xml, renderer=None, framemeta=framemeta, font=font, privacy=NoPrivacyZone())
    # Call the factory to trigger actual parsing
    entry = lambda: Entry(datetime.now(timezone.utc))
    return factory(entry)


def test_frame_missing_width_raises():
    xml = """<layout>
        <frame name="test-frame">
            <component type="metric" metric="speed" units="mph" size="32" x="0" y="0"/>
        </frame>
    </layout>"""
    with pytest.raises(IOError, match="test-frame"):
        parse_xml(xml)


def test_frame_with_dimensions_ok():
    xml = """<layout>
        <frame name="ok-frame" width="100" height="50" x="0" y="0">
            <component type="metric" metric="speed" units="mph" size="32" x="0" y="0"/>
        </frame>
    </layout>"""
    result = parse_xml(xml)
    assert result is not None
