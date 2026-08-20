"""Contract checks for the privacy-safe browser checkout shell."""

import re

from fastapi.testclient import TestClient


def test_checkout_serves_semantic_page(client: TestClient) -> None:
    response = client.get("/checkout?lang=ja")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<main class="page-shell">' in response.text
    assert 'id="checkout-form"' in response.text
    assert 'id="live-status"' in response.text
    collected_fields = set(
        re.findall(r'<(?:input|select)[^>]+name="([^"]+)"', response.text)
    )
    assert collected_fields == {
        "merchantReference",
        "amount",
        "currency",
        "outcome",
    }


def test_checkout_serves_browser_assets(client: TestClient) -> None:
    for asset, media_type in [
        ("checkout.js", "text/javascript"),
        ("money.js", "text/javascript"),
        ("styles.css", "text/css"),
    ]:
        response = client.get(f"/checkout/assets/{asset}")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(media_type)


def test_checkout_is_not_added_to_payment_openapi_contract(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/checkout" not in paths
