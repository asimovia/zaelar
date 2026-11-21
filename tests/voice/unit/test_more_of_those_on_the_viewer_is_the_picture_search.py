"""«More of those» on the picture viewer is the picture search, whatever tool the model reached for (pass 110, I2).

«cool, show me a few more of those» came right after the F40 photos, whose search was still loading — the model's
window did not hold them yet, so it said «let me pull a few more 27-inch 4K options» and a listing search opened a
SECOND monitors sheet that broke I3, I4 and the S block. The verdict read `imagenes:add` at 0.99. A sure verdict
on the viewer's `add` is more of the search under way (or last made); its `show` is his words, on an empty viewer.
"""
from __future__ import annotations



def test_the_search_records_what_it_is_looking_for():
    src = open("nucleo/acts/images.py", encoding="utf-8").read()
    i = src.index("async def execute(")
    assert src.index('LAST_QUERY["q"] = q', i) < src.index("_bs.images(", i), "recorded BEFORE the search runs"
