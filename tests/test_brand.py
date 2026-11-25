"""The integration ships its own brand icon, which Home Assistant serves locally."""

from homeassistant.setup import async_setup_component

async def test_brand_icon_served(hass, hass_client):
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()
    resp = await client.get("/api/brands/integration/atc_cala/icon.png")
    assert resp.status == 200, resp.status
    body = await resp.read()
    assert body == open("custom_components/atc_cala/brand/icon.png", "rb").read()
    resp = await client.get("/api/brands/integration/atc_cala/dark_icon@2x.png")
    assert resp.status == 200 and await resp.read() == body  # falls back to icon.png
