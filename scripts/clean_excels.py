

"""Reescreve os 3 Excels brutos em formato tabular (uma linha por ano).

Roda uma vez, sobrescrevendo os arquivos em app/data/. Os arquivos originais
foram baixados com cabeçalhos do IBGE/DATAPREV (linhas de título, multi-índice,
notas de rodapé) que tornam impossível usá-los direto numa regressão.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"


def clean_acidentes() -> pd.DataFrame:
    raw = pd.read_excel(DATA_DIR / "acidentes.xlsx", header=None)
    rows = raw.iloc[6:9, [1, 2, 3, 4, 5, 6, 7, 8]].copy()
    rows.columns = [
        "ano",
        "total",
        "branca",
        "preta",
        "parda",
        "amarela",
        "indigena",
        "ignorada",
    ]
    rows["ano"] = rows["ano"].astype(int)
    for c in rows.columns[1:]:
        rows[c] = rows[c].astype(int)
    return rows.reset_index(drop=True)


def clean_inovacao() -> pd.DataFrame:
    path = DATA_DIR / "inovacao_e_tecnologia.xlsx"
    sheets = pd.ExcelFile(path).sheet_names
    frames = []
    for sheet in sheets:
        df = pd.read_excel(path, sheet_name=sheet, header=0)
        df = df.rename(
            columns={
                "estado": "estado",
                "índice": "indice",
                "Índice": "indice",
                "IBID - Contexto": "ibid_contexto",
                "Instituições": "instituicoes",
                "Capital humano": "capital_humano",
                "Infraestrutura": "infraestrutura",
                "Economia": "economia",
                "Negócios": "negocios",
                "IBID - Resultado": "ibid_resultado",
                "Conhecimento e tecnologia": "conhecimento_tecnologia",
                "Economia criativa": "economia_criativa",
            }
        )
        df["ano"] = int(sheet)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = out[out["estado"].str.strip().str.lower() == "brasil"].copy()
    cols = [
        "ano",
        "indice",
        "ibid_contexto",
        "instituicoes",
        "capital_humano",
        "infraestrutura",
        "economia",
        "negocios",
        "ibid_resultado",
        "conhecimento_tecnologia",
        "economia_criativa",
    ]
    return out[cols].sort_values("ano").reset_index(drop=True)


def clean_instrucao() -> pd.DataFrame:
    raw = pd.read_excel(
        DATA_DIR / "instrucao_e_populacao.xlsx",
        sheet_name="instrucao",
        header=None,
    )
    years = [int(y) for y in raw.iloc[1, 2:5].tolist()]
    levels = {
        "Total": "total",
        "Sem instrução": "sem_instrucao",
        "Ensino fundamental incompleto ou equivalente": "fundamental_incompleto",
        "Ensino fundamental completo ou equivalente": "fundamental_completo",
        "Ensino médio incompleto ou equivalente": "medio_incompleto",
        "Ensino médio completo ou equivalente": "medio_completo",
        "Ensino superior incompleto ou equivalente": "superior_incompleto",
        "Superior completo": "superior_completo",
    }
    rows = []
    for ano_idx, ano in enumerate(years):
        rec = {"ano": ano}
        for src_label, col_name in levels.items():
            mask = raw.iloc[:, 1].astype(str).str.strip() == src_label
            if mask.any():
                rec[col_name] = float(raw.loc[mask, 2 + ano_idx].iloc[0])
        rows.append(rec)
    df = pd.DataFrame(rows)
    return df.sort_values("ano").reset_index(drop=True)


def main() -> None:
    acidentes = clean_acidentes()
    inovacao = clean_inovacao()
    instrucao = clean_instrucao()

    acidentes.to_excel(DATA_DIR / "acidentes.xlsx", index=False)
    inovacao.to_excel(DATA_DIR / "inovacao_e_tecnologia.xlsx", index=False)
    instrucao.to_excel(DATA_DIR / "instrucao_e_populacao.xlsx", index=False)

    print("acidentes\n", acidentes, "\n")
    print("inovacao\n", inovacao, "\n")
    print("instrucao\n", instrucao, "\n")


if __name__ == "__main__":
    main()
