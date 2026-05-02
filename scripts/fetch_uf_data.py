"""Coleta dados socioeconômicos por UF e gera um Excel consolidado para regressão.

Variáveis (Y e X) e fontes:
- Acidentes do trabalho com CAT registrada, 2023, por UF -> AEAT 2023 (DATAPREV/MPS)
- População residente estimada, 2024, por UF                -> IBGE API tab 6579 v 9324
- PIB e VAB (total + indústria), 2021, por UF               -> IBGE API tab 5938 v 37, 498, 517
- IDHM 2021 (geral, renda, longevidade, educação)           -> Wikipedia (PNUD/IPEA/FJP)
- Índice de Gini do rendimento domiciliar pc, 2023, por UF  -> Wikipedia (IBGE PNAD-C)
- IBID 2024 por UF (mantido como referência adicional)      -> INPI/MCTI

Saída: app/data/dados_por_uf.xlsx
Pré-requisito: app/data/aeat_2023/ já extraído por scripts/download_aeat.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "app" / "data"
AEAT_DIR = DATA_DIR / "aeat_2023" / "Seção I - A_xlsx"


CHAPTER_TO_UF = {
    2: "RO", 3: "AC", 4: "AM", 5: "RR", 6: "PA", 7: "AP", 8: "TO",
    9: "MA", 10: "PI", 11: "CE", 12: "RN", 13: "PB", 14: "PE", 15: "AL",
    16: "SE", 17: "BA", 18: "MG", 19: "ES", 20: "RJ", 21: "SP",
    22: "PR", 23: "SC", 24: "RS",
    25: "MS", 26: "MT", 27: "GO", 28: "DF",
}

UF_NAME = {
    "RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima",
    "PA": "Pará", "AP": "Amapá", "TO": "Tocantins",
    "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará", "RN": "Rio Grande do Norte",
    "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas", "SE": "Sergipe", "BA": "Bahia",
    "MG": "Minas Gerais", "ES": "Espírito Santo", "RJ": "Rio de Janeiro", "SP": "São Paulo",
    "PR": "Paraná", "SC": "Santa Catarina", "RS": "Rio Grande do Sul",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "GO": "Goiás", "DF": "Distrito Federal",
}
NAME_TO_UF = {v: k for k, v in UF_NAME.items()}


# IDHM 2021 (PNUD/IPEA/FJP, via Wikipedia) — overall, renda, longevidade, educação
IDHM_2021 = {
    "DF": (0.814, 0.821, 0.803, 0.817),
    "SP": (0.806, 0.771, 0.810, 0.839),
    "SC": (0.792, 0.759, 0.827, 0.790),
    "MG": (0.774, 0.718, 0.846, 0.762),
    "ES": (0.771, 0.744, 0.864, 0.715),
    "RS": (0.771, 0.767, 0.797, 0.750),
    "PR": (0.769, 0.744, 0.785, 0.780),
    "RJ": (0.762, 0.759, 0.769, 0.758),
    "MS": (0.742, 0.733, 0.751, 0.741),
    "GO": (0.737, 0.714, 0.721, 0.778),
    "MT": (0.736, 0.720, 0.730, 0.758),
    "CE": (0.734, 0.658, 0.784, 0.766),
    "TO": (0.731, 0.684, 0.779, 0.732),
    "RN": (0.728, 0.692, 0.819, 0.680),
    "PE": (0.719, 0.675, 0.751, 0.758),
    "AC": (0.710, 0.671, 0.746, 0.777),
    "SE": (0.702, 0.672, 0.722, 0.781),
    "AM": (0.700, 0.677, 0.727, 0.805),
    "RO": (0.700, 0.712, 0.739, 0.800),
    "RR": (0.699, 0.695, 0.739, 0.809),
    "PB": (0.698, 0.656, 0.714, 0.783),
    "BA": (0.691, 0.663, 0.724, 0.783),
    "PA": (0.690, 0.646, 0.719, 0.789),
    "PI": (0.690, 0.635, 0.708, 0.777),
    "AP": (0.688, 0.694, 0.724, 0.813),
    "AL": (0.684, 0.641, 0.694, 0.755),
    "MA": (0.676, 0.612, 0.699, 0.757),
}

# Índice de Gini do rendimento mensal real domiciliar per capita, 2023 (IBGE PNAD-C)
GINI_2023 = {
    "PB": 0.559, "PI": 0.552, "DF": 0.543, "RJ": 0.540, "RN": 0.535,
    "RR": 0.520, "CE": 0.513, "AM": 0.512, "AC": 0.511, "SE": 0.507,
    "SP": 0.504, "PA": 0.501, "PE": 0.496, "MA": 0.492, "AP": 0.491,
    "BA": 0.490, "AL": 0.486, "ES": 0.486, "MS": 0.477, "TO": 0.477,
    "MG": 0.476, "GO": 0.473, "RS": 0.466, "PR": 0.463, "RO": 0.455,
    "MT": 0.452, "SC": 0.418,
}

# IBID 2024 (INPI/MCTI), índice geral por UF — Fig.6, p.16
IBID_2024 = {
    "SP": 0.891, "SC": 0.415, "PR": 0.406, "RJ": 0.402, "RS": 0.401,
    "MG": 0.378, "DF": 0.304, "ES": 0.268, "GO": 0.252, "MS": 0.228,
    "RN": 0.216, "MT": 0.205, "PE": 0.195, "CE": 0.188, "BA": 0.179,
    "SE": 0.178, "PB": 0.167, "PI": 0.160, "TO": 0.154, "AM": 0.153,
    "AL": 0.143, "RO": 0.143, "RR": 0.135, "PA": 0.133, "AP": 0.132,
    "MA": 0.125, "AC": 0.111,
}


def _http_get(url: str) -> str:
    import gzip

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=60)
    raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def fetch_ibge_series(table: int, period: int, variable: int) -> dict[str, float]:
    url = (
        f"https://servicodados.ibge.gov.br/api/v3/agregados/{table}"
        f"/periodos/{period}/variaveis/{variable}?localidades=N3[all]"
    )
    payload = json.loads(_http_get(url))
    series = payload[0]["resultados"][0]["series"]
    out: dict[str, float] = {}
    for s in series:
        name = s["localidade"]["nome"]
        if name in NAME_TO_UF:
            out[NAME_TO_UF[name]] = float(s["serie"][str(period)])
    return out


def extract_aeat_total(uf: str) -> tuple[int, int]:
    """Retorna (acidentes_total_geral_2023, acidentes_com_cat_registrada_2023)."""
    chapter = next(c for c, s in CHAPTER_TO_UF.items() if s == uf)
    path = AEAT_DIR / f"23Act{chapter:02d}_03.xlsx"
    df = pd.read_excel(path, header=None)
    total_row = df.iloc[8]
    total_geral = int(total_row.iloc[3])
    com_cat = int(total_row.iloc[6])
    return total_geral, com_cat


def main() -> None:
    pop = fetch_ibge_series(6579, 2024, 9324)
    pib = fetch_ibge_series(5938, 2021, 37)
    vab_total = fetch_ibge_series(5938, 2021, 498)
    vab_industria = fetch_ibge_series(5938, 2021, 517)

    rows = []
    for uf in sorted(UF_NAME):
        idhm, idhm_renda, idhm_long, idhm_edu = IDHM_2021[uf]
        total_acid, com_cat = extract_aeat_total(uf)
        rows.append(
            {
                "uf": uf,
                "uf_nome": UF_NAME[uf],
                "populacao_2024": int(pop[uf]),
                "pib_2021": pib[uf],
                "vab_total_2021": vab_total[uf],
                "vab_industria_2021": vab_industria[uf],
                "pct_industria": vab_industria[uf] / vab_total[uf],
                "pib_per_capita_2021": pib[uf] / pop[uf],
                "idhm_2021": idhm,
                "idhm_renda_2021": idhm_renda,
                "idhm_longevidade_2021": idhm_long,
                "idhm_educacao_2021": idhm_edu,
                "gini_2023": GINI_2023[uf],
                "ibid_2024": IBID_2024[uf],
                "acid_total_2023": total_acid,
                "acid_com_cat_2023": com_cat,
                "acid_por_mil_hab_2023": com_cat / pop[uf] * 1000,
            }
        )

    df = pd.DataFrame(rows)
    out_path = DATA_DIR / "dados_por_uf.xlsx"
    df.to_excel(out_path, index=False)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print(df.round(4).to_string())
    print(f"\nsalvo em: {out_path}")


if __name__ == "__main__":
    main()
