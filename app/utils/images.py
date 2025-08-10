import base64
from io import BytesIO
from typing import Literal
from PIL import Image


def encode_plt_to_data_uri(plt, fmt: Literal["png", "webp"] = "png", dpi: int = 120) -> str:
    buf = BytesIO()
    if fmt == "png":
        plt.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
        mime = "image/png"
    else:
        plt.savefig(buf, format="webp", dpi=dpi, bbox_inches="tight")
        mime = "image/webp"
    byt = buf.getvalue()
    b64 = base64.b64encode(byt).decode("ascii")
    return f"data:{mime};base64,{b64}"
