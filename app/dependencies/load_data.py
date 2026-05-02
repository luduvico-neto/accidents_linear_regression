import pandas as pd

from utils import load_data


def load_accidents_data() -> pd.DataFrame:
    return load_data("acidentes.xlsx")


def load_inovation_data() -> pd.DataFrame:
    return load_data("inovacao_e_tecnologia.xlsx")


def load_instruction_and_population_data() -> pd.DataFrame:
    return load_data("instrucao_e_populacao.xlsx")


def load_uf_data() -> pd.DataFrame:
    """Painel cross-section por UF (27 obs) com socioeconômico + acidentes.

    Gerado por scripts/fetch_uf_data.py a partir de IBGE, Wikipedia (IDHM/Gini),
    INPI/MCTI (IBID) e DATAPREV (AEAT).
    """
    return load_data("dados_por_uf.xlsx")
