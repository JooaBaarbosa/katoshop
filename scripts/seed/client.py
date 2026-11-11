"""Cliente HTTP mínimo das APIs de identity e de admin do catálogo, via gateway."""

from typing import Any

import httpx


class SeedError(Exception):
    """Falha que interrompe o seed com mensagem legível."""


def _check(response: httpx.Response, *expected: int) -> httpx.Response:
    if response.status_code not in expected:
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text[:500]
        raise SeedError(
            f"{response.request.method} {response.request.url} respondeu "
            f"{response.status_code}: {body}"
        )
    return response


def staff_login(http: httpx.Client, api_url: str, email: str, password: str) -> str:
    """Login de funcionário (uma vez só: o login tem limite de taxa no gateway)."""
    response = http.post(
        f"{api_url}/identity/v1/auth/staff/login", json={"email": email, "password": password}
    )
    return str(_check(response, 200).json()["access_token"])


class CatalogAdmin:
    def __init__(self, http: httpx.Client, api_url: str, token: str) -> None:
        self._http = http
        self._base = f"{api_url}/catalog/v1/admin"
        self._auth = {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, **params: str) -> Any:
        response = self._http.get(f"{self._base}{path}", params=params, headers=self._auth)
        return _check(response, 200).json()

    def _send(self, method: str, path: str, body: Any, *expected: int) -> Any:
        response = self._http.request(method, f"{self._base}{path}", json=body, headers=self._auth)
        return _check(response, *expected).json()

    # ------------------------------------------------------------------ categorias e coleções

    def categories(self) -> list[dict[str, Any]]:
        return self._get("/categories")["items"]

    def create_category(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("POST", "/categories", body, 201)

    def update_category(self, category_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("PATCH", f"/categories/{category_id}", body, 200)

    def collections(self) -> list[dict[str, Any]]:
        return self._get("/collections")["items"]

    def create_collection(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("POST", "/collections", body, 201)

    def update_collection(self, collection_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("PATCH", f"/collections/{collection_id}", body, 200)

    def set_collection_products(self, collection_id: str, product_ids: list[str]) -> None:
        self._send(
            "PUT", f"/collections/{collection_id}/products", {"product_ids": product_ids}, 200
        )

    # ------------------------------------------------------------------ produtos

    def find_product(self, slug: str) -> dict[str, Any] | None:
        """Busca exata por slug; devolve o produto completo ou None."""
        items = self._get("/products", slug=slug)["items"]
        match = next((item for item in items if item["slug"] == slug), None)
        return None if match is None else self.product(match["id"])

    def product(self, product_id: str) -> dict[str, Any]:
        return self._get(f"/products/{product_id}")

    def create_product(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("POST", "/products", body, 201)

    def update_product(self, product_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("PATCH", f"/products/{product_id}", body, 200)

    def generate_variants(
        self, product_id: str, colors: list[str], sizes: list[str]
    ) -> dict[str, Any]:
        body = {"colors": colors, "sizes": sizes}
        return self._send("POST", f"/products/{product_id}/variants/generate", body, 200)

    def publish(self, product_id: str) -> dict[str, Any]:
        return self._send("POST", f"/products/{product_id}/publish", None, 200)

    # ------------------------------------------------------------------ estoque

    def has_movements(self, variant_id: str) -> bool:
        page = self._get(f"/variants/{variant_id}/stock-movements", limit="1")
        return bool(page["items"])

    def adjust_stock(self, variant_id: str, delta: int, reason: str, note: str) -> None:
        body = {"delta": delta, "reason": reason, "note": note}
        self._send("POST", f"/variants/{variant_id}/stock-adjustments", body, 201)

    # ------------------------------------------------------------------ imagens

    def upload_image(self, product_id: str, data: bytes, fields: dict[str, str]) -> bool:
        """Envia a foto. Devolve True se criou; False se o produto já tinha esses bytes
        (o catálogo regrava o arquivo mesmo assim, o que refaz um volume de mídia perdido)."""
        response = self._http.post(
            f"{self._base}/products/{product_id}/images",
            data=fields,
            files={"file": ("foto.jpg", data, "image/jpeg")},
            headers=self._auth,
        )
        return _check(response, 200, 201).status_code == 201

    def delete_image(self, image_id: str) -> None:
        response = self._http.delete(f"{self._base}/images/{image_id}", headers=self._auth)
        _check(response, 204)

    # ------------------------------------------------------------------ vitrine e painel

    def put_settings(self, settings: dict[str, Any]) -> None:
        self._send("PUT", "/storefront/settings", settings, 200)

    def overview(self) -> dict[str, Any]:
        return self._get("/overview")
