"""Baixa e extrai o AEAT 2023 (DATAPREV/MPS) para app/data/aeat_2023/."""

import io
import urllib.request
import zipfile
from pathlib import Path

URL = "https://www.gov.br/previdencia/pt-br/assuntos/previdencia-social/arquivos/aeat_2023.zip"
OUT_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "aeat_2023"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(OUT_DIR)
    print(f"AEAT 2023 extraído em: {OUT_DIR}")


if __name__ == "__main__":
    main()
