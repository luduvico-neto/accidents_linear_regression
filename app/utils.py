from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_data(file_name: str) -> pd.DataFrame:
    return pd.read_excel(DATA_DIR / file_name)
