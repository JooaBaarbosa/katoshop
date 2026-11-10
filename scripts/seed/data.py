"""Catálogo da loja demo. Nomes, cores e descrições batem com as fotos de images.json.

Todo o conteúdo é demonstrativo: produtos, preços e estoque não existem fora desta demo.
"""

from dataclasses import dataclass
from typing import Any

CLOTHING_SIZES = ("PP", "P", "M", "G", "GG", "XG", "XGG")
# Bonés, gorros e bolsas têm tamanho único; o catálogo só conhece PP..XGG, então usam "M".
ONE_SIZE = ("M",)
SOCK_SIZES = ("P", "M", "G")


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    position: int


@dataclass(frozen=True)
class Collection:
    slug: str
    name: str
    description: str
    featured: bool
    position: int
    product_slugs: tuple[str, ...]


@dataclass(frozen=True)
class Product:
    slug: str
    name: str
    category_slug: str
    base_price_cents: int
    description: str
    attributes: dict[str, str]
    colors: tuple[str, ...]
    sizes: tuple[str, ...]
    # cor -> estoque inicial por tamanho, na ordem de `sizes`
    stock: dict[str, tuple[int, ...]]


CATEGORIES = (
    Category("camisetas", "Camisetas", 0),
    Category("moletons", "Moletons", 1),
    Category("calcas", "Calças", 2),
    Category("acessorios", "Acessórios", 3),
)


def _attrs(material: str, gramatura: str, modelagem: str, cuidados: str) -> dict[str, str]:
    return {
        "material": material,
        "gramatura": gramatura,
        "modelagem": modelagem,
        "cuidados": cuidados,
    }


_MALHA = "Lavar do avesso em água fria. Não usar alvejante. Secar à sombra."
_MOLETOM = "Lavar do avesso em água fria. Não usar secadora. Passar em temperatura baixa."
_SARJA = "Lavar do avesso em água fria. Secar à sombra. Passar em temperatura média."
_TRICO = "Lavar à mão em água fria. Secar na horizontal, longe do sol."
_LONA = "Limpar com pano úmido ou lavar à mão em água fria. Secar à sombra."

PRODUCTS = (
    # ------------------------------------------------------------------ camisetas
    Product(
        slug="camiseta-pesada-preta",
        name="Camiseta pesada preta",
        category_slug="camisetas",
        base_price_cents=12900,
        description=(
            "Camiseta preta lisa de gola careca em malha encorpada. Caimento reto, "
            "ombro levemente caído e costura reforçada na gola para não lacear."
        ),
        attributes=_attrs("100% algodão penteado", "240 g/m²", "Regular", _MALHA),
        colors=("PRT",),
        sizes=CLOTHING_SIZES,
        stock={"PRT": (6, 14, 18, 16, 9, 4, 0)},
    ),
    Product(
        slug="camiseta-pesada-branca",
        name="Camiseta pesada branca",
        category_slug="camisetas",
        base_price_cents=12900,
        description=(
            "A mesma base pesada em branco óptico. Gola careca firme, manga na altura "
            "do bíceps e malha que não fica transparente."
        ),
        attributes=_attrs("100% algodão penteado", "240 g/m²", "Regular", _MALHA),
        colors=("BRC",),
        sizes=CLOTHING_SIZES,
        stock={"BRC": (5, 12, 15, 14, 8, 3, 2)},
    ),
    Product(
        slug="camiseta-basica-off-white",
        name="Camiseta básica off-white",
        category_slug="camisetas",
        base_price_cents=9900,
        description=(
            "Camiseta off-white de malha leve para o calor. Combina com a bermuda de "
            "moletom da mesma cor para um conjunto claro."
        ),
        attributes=_attrs("100% algodão", "180 g/m²", "Regular", _MALHA),
        colors=("OFW",),
        sizes=CLOTHING_SIZES,
        stock={"OFW": (4, 10, 12, 0, 7, 3, 2)},
    ),
    Product(
        slug="camiseta-longline-preta",
        name="Camiseta longline preta",
        category_slug="camisetas",
        base_price_cents=13900,
        description=(
            "Camiseta preta alongada com barra arredondada, mais comprida atrás. "
            "Fica bem por fora da calça e com sobreposição."
        ),
        attributes=_attrs("95% algodão e 5% elastano", "200 g/m²", "Alongada", _MALHA),
        colors=("PRT",),
        sizes=CLOTHING_SIZES,
        stock={"PRT": (0, 0, 0, 0, 0, 0, 0)},
    ),
    Product(
        slug="camiseta-manga-longa-preta",
        name="Camiseta manga longa preta",
        category_slug="camisetas",
        base_price_cents=15900,
        description=(
            "Camiseta preta de manga longa com punho canelado. Serve sozinha na meia "
            "estação e por baixo do moletom no frio."
        ),
        attributes=_attrs("100% algodão penteado", "220 g/m²", "Regular", _MALHA),
        colors=("PRT",),
        sizes=CLOTHING_SIZES,
        stock={"PRT": (3, 8, 11, 10, 6, 0, 1)},
    ),
    Product(
        slug="camiseta-oversized-preta",
        name="Camiseta oversized preta",
        category_slug="camisetas",
        base_price_cents=14900,
        description=(
            "Camiseta preta ampla, com ombro caído e corpo mais largo. Malha pesada "
            "que segura o caimento e não marca."
        ),
        attributes=_attrs("100% algodão", "260 g/m²", "Oversized", _MALHA),
        colors=("PRT",),
        sizes=CLOTHING_SIZES,
        stock={"PRT": (2, 9, 13, 12, 8, 5, 3)},
    ),
    # ------------------------------------------------------------------ moletons
    Product(
        slug="moletom-canguru-pesado",
        name="Moletom canguru pesado",
        category_slug="moletons",
        base_price_cents=32900,
        description=(
            "Moletom com capuz forrado e bolso canguru em felpa pesada. Disponível em "
            "preto e cinza mescla, com punho e barra canelados."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "400 g/m²", "Regular", _MOLETOM
        ),
        colors=("PRT", "CNZ"),
        sizes=CLOTHING_SIZES,
        # R4: o preto tem o M esgotado e os outros tamanhos em estoque.
        stock={
            "PRT": (4, 9, 0, 12, 7, 3, 2),
            "CNZ": (5, 8, 11, 9, 6, 2, 0),
        },
    ),
    Product(
        slug="moletom-canguru-oversized-preto",
        name="Moletom canguru oversized preto",
        category_slug="moletons",
        base_price_cents=34900,
        description=(
            "Moletom preto com capuz em modelagem ampla, manga comprida e bolso "
            "canguru largo. Feito para usar solto."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "420 g/m²", "Oversized", _MOLETOM
        ),
        colors=("PRT",),
        sizes=CLOTHING_SIZES,
        stock={"PRT": (3, 6, 8, 8, 5, 2, 1)},
    ),
    Product(
        slug="moletom-canguru-verde-musgo",
        name="Moletom canguru verde musgo",
        category_slug="moletons",
        base_price_cents=32900,
        description=(
            "Moletom com capuz em verde musgo escuro, bolso canguru e cordão roliço. "
            "A mesma base pesada do canguru preto."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "400 g/m²", "Regular", _MOLETOM
        ),
        colors=("VRD",),
        sizes=CLOTHING_SIZES,
        stock={"VRD": (2, 7, 9, 9, 5, 2, 0)},
    ),
    Product(
        slug="moletom-canguru-off-white",
        name="Moletom canguru off-white",
        category_slug="moletons",
        base_price_cents=32900,
        description=(
            "Moletom off-white com capuz e bolso canguru. Tom cru que não amarela fácil "
            "e combina com calça escura."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "400 g/m²", "Regular", _MOLETOM
        ),
        colors=("OFW",),
        sizes=CLOTHING_SIZES,
        stock={"OFW": (3, 6, 10, 8, 5, 2, 1)},
    ),
    Product(
        slug="moletom-gola-careca-off-white",
        name="Moletom gola careca off-white",
        category_slug="moletons",
        base_price_cents=27900,
        description=(
            "Moletom off-white sem capuz, de ombro caído e corpo amplo. Fica bem com "
            "calça cargo e mochila no dia a dia da cidade."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "380 g/m²", "Ampla", _MOLETOM
        ),
        colors=("OFW",),
        sizes=CLOTHING_SIZES,
        stock={"OFW": (4, 8, 12, 10, 7, 3, 2)},
    ),
    Product(
        slug="moletom-gola-careca-branco",
        name="Moletom gola careca branco",
        category_slug="moletons",
        base_price_cents=26900,
        description=(
            "Moletom branco de gola careca, liso, com punho e barra canelados. A peça "
            "básica para o frio leve."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "360 g/m²", "Regular", _MOLETOM
        ),
        colors=("BRC",),
        sizes=CLOTHING_SIZES,
        stock={"BRC": (0, 5, 9, 8, 6, 2, 1)},
    ),
    # ------------------------------------------------------------------ calças
    Product(
        slug="calca-cargo-preta",
        name="Calça cargo preta",
        category_slug="calcas",
        base_price_cents=29900,
        description=(
            "Calça cargo preta em sarja pesada, com bolsos laterais com lapela e "
            "barra com regulagem."
        ),
        attributes=_attrs("100% algodão, sarja", "300 g/m²", "Reta", _SARJA),
        colors=("PRT",),
        sizes=CLOTHING_SIZES,
        stock={"PRT": (3, 7, 10, 9, 6, 2, 1)},
    ),
    Product(
        slug="calca-cargo-marrom",
        name="Calça cargo marrom",
        category_slug="calcas",
        base_price_cents=29900,
        description=(
            "Calça cargo marrom em sarja de algodão com bolsos laterais. Cor de terra "
            "que esconde bem a sujeira do dia a dia."
        ),
        attributes=_attrs("100% algodão, sarja", "300 g/m²", "Reta", _SARJA),
        colors=("MRR",),
        sizes=CLOTHING_SIZES,
        stock={"MRR": (0, 5, 8, 7, 5, 2, 1)},
    ),
    Product(
        slug="calca-jogger-moletom",
        name="Calça jogger de moletom",
        category_slug="calcas",
        base_price_cents=22900,
        description=(
            "Calça jogger de moletom com cós elástico, cordão e punho no tornozelo. "
            "Em preto e cinza mescla."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "340 g/m²", "Jogger", _MOLETOM
        ),
        colors=("PRT", "CNZ"),
        sizes=CLOTHING_SIZES,
        stock={
            "PRT": (5, 9, 12, 11, 7, 3, 2),
            "CNZ": (4, 8, 10, 9, 6, 0, 1),
        },
    ),
    Product(
        slug="calca-moletom-wide-cinza",
        name="Calça de moletom wide cinza",
        category_slug="calcas",
        base_price_cents=24900,
        description=(
            "Calça de moletom cinza claro de perna larga, com cós alto e elástico. "
            "Forma conjunto com um moletom da mesma cor."
        ),
        attributes=_attrs(
            "80% algodão e 20% poliéster, felpado por dentro", "340 g/m²", "Wide", _MOLETOM
        ),
        colors=("CNZ",),
        sizes=CLOTHING_SIZES,
        stock={"CNZ": (3, 6, 8, 7, 4, 2, 0)},
    ),
    Product(
        slug="bermuda-moletom",
        name="Bermuda de moletom",
        category_slug="calcas",
        base_price_cents=15900,
        description=(
            "Bermuda de moletom com cós elástico e bolsos laterais, acima do joelho. "
            "Em cinza mescla e off-white."
        ),
        attributes=_attrs("100% algodão, moletom flanelado", "300 g/m²", "Regular", _MOLETOM),
        colors=("CNZ", "OFW"),
        sizes=CLOTHING_SIZES,
        stock={
            "CNZ": (4, 8, 10, 9, 6, 3, 1),
            "OFW": (0, 6, 8, 7, 5, 2, 1),
        },
    ),
    # ------------------------------------------------------------------ acessórios
    Product(
        slug="gorro-canelado",
        name="Gorro canelado",
        category_slug="acessorios",
        base_price_cents=8900,
        description=(
            "Gorro de tricô canelado com barra dobrada, em preto e verde musgo. Tamanho único."
        ),
        attributes=_attrs("100% acrílico", "Tricô canelado", "Tamanho único", _TRICO),
        colors=("PRT", "VRD"),
        sizes=ONE_SIZE,
        stock={"PRT": (25,), "VRD": (14,)},
    ),
    Product(
        slug="bone-lavado-cinza",
        name="Boné lavado cinza",
        category_slug="acessorios",
        base_price_cents=11900,
        description=(
            "Boné de seis gomos em algodão lavado cinza, aba curva e fecho ajustável "
            "atrás. Tamanho único."
        ),
        attributes=_attrs("100% algodão lavado", "Sarja leve", "Tamanho único, ajustável", _SARJA),
        colors=("CNZ",),
        sizes=ONE_SIZE,
        stock={"CNZ": (18,)},
    ),
    Product(
        slug="bone-trucker-branco",
        name="Boné trucker branco",
        category_slug="acessorios",
        base_price_cents=9900,
        description=(
            "Boné trucker branco com frente em espuma e tela traseira, fecho de "
            "pressão. Tamanho único."
        ),
        attributes=_attrs(
            "Frente em espuma de poliéster, tela de poliéster",
            "Leve",
            "Tamanho único, ajustável",
            "Limpar com pano úmido. Não lavar na máquina.",
        ),
        colors=("BRC",),
        sizes=ONE_SIZE,
        stock={"BRC": (0,)},
    ),
    Product(
        slug="meia-cano-medio-branca",
        name="Meia cano médio branca",
        category_slug="acessorios",
        base_price_cents=6900,
        description=(
            "Meia branca de cano médio com sola atoalhada. Tamanhos P (34 a 37), "
            "M (38 a 41) e G (42 a 44)."
        ),
        attributes=_attrs(
            "75% algodão, 23% poliamida e 2% elastano",
            "Sola atoalhada",
            "Cano médio",
            _MALHA,
        ),
        colors=("BRC",),
        sizes=SOCK_SIZES,
        stock={"BRC": (20, 30, 24)},
    ),
    Product(
        slug="meia-canelada-cinza",
        name="Meia canelada cinza",
        category_slug="acessorios",
        base_price_cents=6900,
        description=(
            "Meia canelada cinza mescla de cano alto. Tamanhos P (34 a 37), M (38 a 41) "
            "e G (42 a 44)."
        ),
        attributes=_attrs(
            "75% algodão, 23% poliamida e 2% elastano", "Canelada", "Cano alto", _MALHA
        ),
        colors=("CNZ",),
        sizes=SOCK_SIZES,
        stock={"CNZ": (15, 0, 18)},
    ),
    Product(
        slug="bolsa-transversal-preta",
        name="Bolsa transversal preta",
        category_slug="acessorios",
        base_price_cents=18900,
        description=(
            "Bolsa transversal preta compacta, com zíper duplo e alça longa regulável. "
            "Cabe celular, carteira e chaves."
        ),
        attributes=_attrs(
            "Material sintético com forro de poliéster",
            "Compacta",
            "Tamanho único",
            _LONA,
        ),
        colors=("PRT",),
        sizes=ONE_SIZE,
        stock={"PRT": (12,)},
    ),
    Product(
        slug="ecobag-lona-crua",
        name="Ecobag de lona crua",
        category_slug="acessorios",
        base_price_cents=7900,
        description=("Ecobag lisa de lona de algodão cru com alças longas para levar no ombro."),
        attributes=_attrs("100% algodão, lona", "Lona encorpada", "Tamanho único", _LONA),
        colors=("OFW",),
        sizes=ONE_SIZE,
        stock={"OFW": (30,)},
    ),
)

COLLECTIONS = (
    Collection(
        slug="drop-inverno-26",
        name="Drop Inverno 26",
        description="Moletons pesados, calças cargo e gorros para o frio.",
        featured=True,
        position=0,
        product_slugs=(
            "moletom-gola-careca-off-white",
            "moletom-canguru-pesado",
            "moletom-canguru-verde-musgo",
            "calca-cargo-marrom",
            "gorro-canelado",
            "moletom-canguru-off-white",
            "calca-cargo-preta",
        ),
    ),
    Collection(
        slug="basicos-pesados",
        name="Básicos pesados",
        description="Camisetas, joggers e meias que entram em qualquer combinação.",
        featured=True,
        position=1,
        product_slugs=(
            "camiseta-pesada-preta",
            "camiseta-pesada-branca",
            "camiseta-basica-off-white",
            "camiseta-manga-longa-preta",
            "calca-jogger-moletom",
            "bermuda-moletom",
            "meia-cano-medio-branca",
            "meia-canelada-cinza",
        ),
    ),
    Collection(
        slug="rua-a-noite",
        name="Rua à noite",
        description="Peças escuras para sair depois que o sol se põe.",
        featured=True,
        position=2,
        product_slugs=(
            "moletom-canguru-oversized-preto",
            "camiseta-oversized-preta",
            "camiseta-longline-preta",
            "calca-cargo-preta",
            "bolsa-transversal-preta",
            "bone-lavado-cinza",
        ),
    ),
)

# Foto do hero: pessoa de streetwear numa rua de Nova York (também é foto de produto).
HERO_IMAGE_ID = "unsplash-EIOmriN64sU"


def storefront_settings(hero_image_key: str) -> dict[str, Any]:
    """Configuração da vitrine; a chave da imagem do hero vem do hash da foto."""
    return {
        "hero": {
            "title": "Streetwear para andar, não para guardar",
            "subtitle": "Camisetas, moletons e calças em tecido pesado, do P ao XGG",
            "cta_label": "Ver o drop atual",
            "cta_href": "/colecoes/drop-inverno-26",
            "image_key": hero_image_key,
        },
        "secondary_cta": {"label": "Todas as peças", "href": "/busca"},
        "featured_collection_slugs": [c.slug for c in COLLECTIONS],
        "policies": {
            "shipping_text": "Frete calculado pelo CEP no carrinho. Pedidos demo não são enviados.",
            "returns_text": "Troca ou devolução em até 7 dias após o recebimento.",
            "pix_discount_percent": 5,
            "max_installments": 3,
            "demo_notice": "Loja demonstrativa, nenhuma compra é real",
        },
    }
