"""A commission that lands on the picture viewer is the picture TOOL, never a worker (node 2.187).

Demo passes 60-62, B1 (2026-09-29): «now let's make it prettier, find me the wallpaper cosmic eye in the sky by
tyler young, the orion nebula» was escalated to a Brain Worker; passes 56-59 ran it as `show_images` in 3 s and B2
set it as the wallpaper. The late catalogue question could not name the viewer (its criterion was cut before the
word «wallpaper»; now it leads with it), and even named, the viewer's `show` needs pictures a TURN TOOL finds — so
the commission pass's «show {query}» becomes the `show_images` request instead of a data-op that returns «no
pictures arrived».
"""


SAID = "now let's make it prettier, find me the wallpaper cosmic eye in the sky by tyler young, the orion nebula"


def test_wallpaper_names_the_viewer():
    from widgets import runtime
    assert runtime.identify_named("set that as my wallpaper") == "imagenes"
    assert runtime.identify_named("ponlo de fondo de pantalla") == "imagenes"

