"""A desktop is landscape: a wallpaper search puts wider-than-tall pictures first (demo pass 2026-09-28, B2).

«find me a deep space wallpaper, like a blue nebula» — none of the six was ≥1600 px wide, so the order was area
alone, and a PHONE wallpaper (800x1422) came first; «set the first one as my background» stretched it across a
1600x1000 desk, blurred and cropped."""
import asyncio


def test_the_landscape_picture_leads_a_wallpaper_search(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.imagenes import data as img
    pics = [{"url": "https://x/phone.jpg", "title": "phone", "w": 800, "h": 1422},
            {"url": "https://x/wide.jpg", "title": "wide", "w": 1280, "h": 720},
            {"url": "https://x/small.jpg", "title": "small", "w": 640, "h": 360}]

    async def images(q, n):
        return {"items": pics, "source": "google"}
    import search.browser as bs
    monkeypatch.setattr(bs, "images", images)

    async def brain_action(wid, act, payload):
        return img.apply_action(act, payload)
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    from nucleo.flash import image_turn as it
    parte = asyncio.run(it.execute("blue nebula deep space wallpaper", 6))
    assert parte["ok"] and parte["first"] == "wide", parte
    assert [i["title"] for i in store.load("imagenes", {})["items"]] == ["wide", "small", "phone"]


def test_a_picture_that_can_become_the_backdrop_leads(tmp_path, monkeypatch):
    """full17 B2: the first nebula's site answered 403 to a download; «set the first one» kept the remote URL, the
    browser was refused it too, and the desk stayed bare while the reply said it was set."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets import desktop_props as dp
    from widgets.imagenes import data as img
    pics = [{"url": "https://blocked/a.jpg", "title": "blocked", "w": 3000, "h": 1694},
            {"url": "https://open/b.jpg", "title": "open", "w": 2560, "h": 1440}]

    async def images(q, n):
        return {"items": pics, "source": "google"}
    import search.browser as bs
    monkeypatch.setattr(bs, "images", images)
    monkeypatch.setattr(dp, "fetchable", lambda url, timeout=2.5: "open" in url)

    async def brain_action(wid, act, payload):
        return img.apply_action(act, payload)
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    from nucleo.flash import image_turn as it
    parte = asyncio.run(it.execute("deep space nebula wallpaper", 6))
    assert parte["first"] == "open", parte


def test_a_backdrop_that_could_not_be_copied_is_said_not_announced(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets import desktop_props as dp
    from widgets.imagenes import data as img
    monkeypatch.setattr(dp, "set_wallpaper", lambda url, title="": {"url": url, "title": title, "copied": False})
    store.save("imagenes", {"items": [{"url": "https://blocked/a.jpg", "title": "nebula", "site": "blocked.example",
                                       "w": 3000, "h": 1694}], "i": 0})
    got = img.apply_action("wallpaper", {"item": 1})
    assert got["ok"] and "blocked.example" in got.get("warning", ""), got


def test_the_picture_he_named_leads_one_a_little_bigger(tmp_path, monkeypatch):
    """Demo sandbox 2026-11-13, B2 on b137: «find me the wallpaper quiet lantern in the dark by rowan vale» — the sort by
    area alone put a 1920x1200 «Cosmic Nebula … by Rowan Vale» before the 1920x1084 «Lagoon Nebula HD - Cosmic Eye in
    the Sky», and «set the first one» set the wrong one. Among desk-sized pictures the title that carries more of his
    search leads; a thumbnail of it does not. Disarm: drop the title term from the sort key → red."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.imagenes import data as img
    pics = [{"url": "https://x/a.jpg", "title": "Cosmic Nebula: HD Sci-Fi Wallpaper by Rowan Vale", "w": 1920, "h": 1200},
            {"url": "https://x/b.jpg", "title": "Lagoon Nebula HD - Quiet Lantern in the Dark by Rowan Vale", "w": 1920, "h": 1084},
            {"url": "https://x/c.jpg", "title": "Lagoon Nebula HD - Quiet Lantern in the Dark by Rowan Vale (thumb)", "w": 350, "h": 219},
            {"url": "https://x/d.jpg", "title": "Some space wallpaper", "w": 2560, "h": 1600}]

    async def images(q, n):
        return {"items": pics, "source": "google"}
    import search.browser as bs
    monkeypatch.setattr(bs, "images", images)

    async def brain_action(wid, act, payload):
        return img.apply_action(act, payload)
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    from nucleo.flash import image_turn as it
    asyncio.run(it.execute("Quiet Lantern in the Dark by Rowan Vale Lagoon Nebula wallpaper", 6))
    got = [i["url"] for i in store.load("imagenes", {})["items"]]
    assert got[:2] == ["https://x/b.jpg", "https://x/a.jpg"] and "https://x/c.jpg" not in got[:2], got
