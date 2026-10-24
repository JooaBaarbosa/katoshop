import io
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from PIL import Image

from catalog.settings import CatalogSettings

type Json = dict[str, Any]
type MakeProduct = Callable[..., Awaitable[Json]]

ALT = "Moletom preto visto de frente"
MISSING_ID = "0197c1c1-0000-7000-8000-000000000000"


def image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (64, 48), color: str = "black") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


async def upload(
    client: httpx.AsyncClient,
    product_id: str,
    data: bytes,
    *,
    filename: str = "foto.jpg",
    **fields: str,
) -> httpx.Response:
    form = {"alt": ALT, **fields}
    return await client.post(
        f"/v1/admin/products/{product_id}/images",
        files={"file": (filename, data, "application/octet-stream")},
        data=form,
    )


async def test_upload_jpeg_ok_records_dimensions(
    admin_client: httpx.AsyncClient, make_product: MakeProduct, settings: CatalogSettings
) -> None:
    product = await make_product()
    response = await upload(
        admin_client,
        product["id"],
        image_bytes(),
        color_code="PRT",
        credit_author="Fulana",
        credit_source_url="https://example.com/foto",
        license="CC0",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["width"], body["height"]) == (64, 48)
    assert body["alt"] == ALT
    assert body["color_code"] == "PRT"
    assert body["credit_author"] == "Fulana"
    assert body["storage_key"].startswith("products/")
    assert body["storage_key"].endswith(".jpg")
    assert body["url"] == f"{settings.public_base_url}/v1/media/{body['storage_key']}"
    assert (settings.media_root / body["storage_key"]).is_file()
    fetched = await admin_client.get(f"/v1/admin/products/{product['id']}")
    assert [i["id"] for i in fetched.json()["images"]] == [body["id"]]
    assert fetched.json()["images"][0]["url"] == body["url"]


async def test_upload_png_and_webp_detected_by_content(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    png = await upload(admin_client, product["id"], image_bytes("PNG"), filename="a.bin")
    webp = await upload(admin_client, product["id"], image_bytes("WEBP"), filename="b.jpg")
    assert png.json()["storage_key"].endswith(".png")
    assert webp.json()["storage_key"].endswith(".webp")
    assert png.json()["position"] == 0
    assert webp.json()["position"] == 1


async def test_upload_pdf_renamed_jpg_415(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    response = await upload(admin_client, product["id"], b"%PDF-1.7\n" + b"x" * 100)
    assert response.status_code == 415
    assert response.json()["code"] == "catalog.image.unsupported_type"


async def test_upload_corrupt_image_with_valid_magic_415(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    response = await upload(admin_client, product["id"], b"\x89PNG\r\n\x1a\n" + b"lixo" * 50)
    assert response.status_code == 415
    assert response.json()["code"] == "catalog.image.unsupported_type"


async def test_upload_over_8mb_413(
    admin_client: httpx.AsyncClient, make_product: MakeProduct, settings: CatalogSettings
) -> None:
    product = await make_product()
    big = b"\xff\xd8\xff" + b"\x00" * (8 * 1024 * 1024)
    response = await upload(admin_client, product["id"], big)
    assert response.status_code == 413
    assert response.json()["code"] == "catalog.image.too_large"
    assert not settings.media_root.exists()


async def test_upload_exactly_8mb_is_not_too_large(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    data = b"\xff\xd8\xff" + b"\x00" * (8 * 1024 * 1024 - 3)
    response = await upload(admin_client, product["id"], data)
    assert response.status_code == 415  # cabe no limite, mas não é uma imagem decodificável


async def test_upload_same_bytes_twice_returns_existing(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    data = image_bytes()
    first = await upload(admin_client, product["id"], data)
    second = await upload(admin_client, product["id"], data, color_code="PRT")
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    fetched = await admin_client.get(f"/v1/admin/products/{product['id']}")
    assert len(fetched.json()["images"]) == 1


async def test_same_bytes_on_other_product_creates_new_row(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    one, two = await make_product(), await make_product()
    data = image_bytes()
    first = await upload(admin_client, one["id"], data)
    second = await upload(admin_client, two["id"], data)
    assert second.status_code == 201
    assert second.json()["storage_key"] == first.json()["storage_key"]
    assert second.json()["id"] != first.json()["id"]


async def test_upload_empty_alt_422(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    for alt in ("", "   "):
        response = await upload(admin_client, product["id"], image_bytes(), alt=alt)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "catalog.image.alt_required"


async def test_upload_missing_alt_or_file_422(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    no_alt = await admin_client.post(
        f"/v1/admin/products/{product['id']}/images",
        files={"file": ("a.jpg", image_bytes(), "image/jpeg")},
    )
    no_file = await admin_client.post(
        f"/v1/admin/products/{product['id']}/images", data={"alt": ALT}
    )
    assert no_alt.status_code == 422
    assert no_file.status_code == 422


async def test_upload_unknown_color_422_and_unknown_product_404(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    color = await upload(admin_client, product["id"], image_bytes(), color_code="ZZZ")
    missing = await upload(admin_client, MISSING_ID, image_bytes())
    assert color.status_code == 422
    assert color.json()["code"] == "catalog.image.unknown_color"
    assert missing.status_code == 404
    assert missing.json()["code"] == "catalog.product.not_found"


async def test_upload_requires_catalog_write(
    client: httpx.AsyncClient, customer_token: str
) -> None:
    anonymous = await upload(client, MISSING_ID, image_bytes())
    assert anonymous.status_code == 401
    client.headers["Authorization"] = f"Bearer {customer_token}"
    forbidden = await upload(client, MISSING_ID, image_bytes())
    assert forbidden.status_code == 403


async def test_patch_image_updates_fields(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    image = (await upload(admin_client, product["id"], image_bytes())).json()
    response = await admin_client.patch(
        f"/v1/admin/images/{image['id']}",
        json={"alt": "Novo alt", "color_code": "PRT", "position": 3, "license": "CC-BY"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["alt"], body["color_code"], body["position"], body["license"]) == (
        "Novo alt",
        "PRT",
        3,
        "CC-BY",
    )
    cleared = await admin_client.patch(f"/v1/admin/images/{image['id']}", json={"color_code": None})
    assert cleared.json()["color_code"] is None


async def test_patch_image_rejects_bad_input(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    image = (await upload(admin_client, product["id"], image_bytes())).json()
    url = f"/v1/admin/images/{image['id']}"
    assert (await admin_client.patch(url, json={"alt": "  "})).status_code == 422
    assert (await admin_client.patch(url, json={"alt": None})).status_code == 422
    assert (await admin_client.patch(url, json={"storage_key": "x"})).status_code == 422
    assert (await admin_client.patch(url, json={"position": -1})).status_code == 422
    unknown = await admin_client.patch(url, json={"color_code": "ZZZ"})
    assert unknown.status_code == 422
    missing = await admin_client.patch(f"/v1/admin/images/{MISSING_ID}", json={"alt": "x"})
    assert missing.status_code == 404
    assert missing.json()["code"] == "catalog.image.not_found"


async def test_delete_image_removes_row_but_keeps_file(
    admin_client: httpx.AsyncClient, make_product: MakeProduct, settings: CatalogSettings
) -> None:
    product = await make_product()
    image = (await upload(admin_client, product["id"], image_bytes())).json()
    response = await admin_client.delete(f"/v1/admin/images/{image['id']}")
    assert response.status_code == 204
    fetched = await admin_client.get(f"/v1/admin/products/{product['id']}")
    assert fetched.json()["images"] == []
    # conteúdo endereçado por hash: o arquivo pode ser compartilhado e fica
    assert (settings.media_root / image["storage_key"]).is_file()
    again = await admin_client.delete(f"/v1/admin/images/{image['id']}")
    assert again.status_code == 404
    assert again.json()["code"] == "catalog.image.not_found"


async def test_upload_decompression_bomb_415(
    admin_client: httpx.AsyncClient, make_product: MakeProduct
) -> None:
    product = await make_product()
    buffer = io.BytesIO()
    # 10000 x 10000 bilevel: poucos KB em disco, mais pixels que o limite do Pillow.
    Image.new("1", (10000, 10000)).save(buffer, format="PNG")
    response = await upload(admin_client, product["id"], buffer.getvalue())
    assert response.status_code == 415
    assert response.json()["code"] == "catalog.image.unsupported_type"


async def test_reupload_restores_missing_file(
    admin_client: httpx.AsyncClient, make_product: MakeProduct, settings: CatalogSettings
) -> None:
    product = await make_product()
    data = image_bytes()
    first = (await upload(admin_client, product["id"], data)).json()
    path = settings.media_root / first["storage_key"]
    path.unlink()
    again = await upload(admin_client, product["id"], data)
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert path.read_bytes() == data


async def test_openapi_declares_multipart_upload(app: Any) -> None:
    post = app.openapi()["paths"]["/v1/admin/products/{product_id}/images"]["post"]
    schema = post["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert {"file", "alt"} <= set(schema["required"])
    assert {"file", "alt", "color_code", "license"} <= set(schema["properties"])
    assert "200" in post["responses"]
