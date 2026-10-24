"""Validação de imagens com Pillow (síncrona; chame em thread)."""

import io

from PIL import Image

_MAX_PIXELS = Image.MAX_IMAGE_PIXELS or 89_478_485


class InvalidImageError(Exception):
    pass


def probe_image(data: bytes) -> tuple[int, int]:
    """Devolve (largura, altura) ou levanta `InvalidImageError` (corrompida ou bomba)."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            # Com filterwarnings=error o aviso de bomba chega como exceção; em produção ele só
            # avisaria, então o limite é aplicado também aqui.
            if width < 1 or height < 1 or width * height > _MAX_PIXELS:
                raise InvalidImageError("dimensions out of range")
            image.verify()
    except InvalidImageError:
        raise
    except (
        OSError,  # inclui UnidentifiedImageError
        SyntaxError,  # verify() de PNG
        ValueError,
        EOFError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImageError(str(exc)) from exc
    return width, height
