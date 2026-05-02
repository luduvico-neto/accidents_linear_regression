"""Regressão linear múltipla: variáveis socioeconômicas -> taxa de acidentes do trabalho.

Modelo: acid_por_mil_hab_2023 = β₀ + β₁·idhm + β₂·gini + β₃·pct_industria
                                  + β₄·pib_per_capita + ε

Dados: 27 UFs do Brasil (cross-section). Veja scripts/fetch_uf_data.py para fontes.

Sem dependência de scipy/statsmodels: cálculo OLS via numpy. t-statísticas reportadas
(|t| > ~2.07 ≈ p < 0.05 com df = 22).
"""

import numpy as np
import pandas as pd

from dependencies.load_data import load_uf_data

TARGET = "acid_por_mil_hab_2023"
FEATURES = ["idhm_2021", "gini_2023", "pct_industria", "pib_per_capita_2021"]


def fit_ols(X: np.ndarray, y: np.ndarray) -> dict:
    n, k = X.shape
    Xd = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    y_hat = Xd @ beta
    residuos = y - y_hat
    df_resid = n - (k + 1)
    ss_res = float((residuos**2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot
    r2_adj = 1.0 - (1.0 - r2) * (n - 1) / df_resid
    sigma2 = ss_res / df_resid
    cov = sigma2 * np.linalg.inv(Xd.T @ Xd)
    se = np.sqrt(np.diag(cov))
    t = beta / se
    f_stat = (r2 / k) / ((1 - r2) / df_resid)
    return {
        "beta": beta, "se": se, "t": t, "y_hat": y_hat, "residuos": residuos,
        "r2": r2, "r2_adj": r2_adj, "f": f_stat, "df_resid": df_resid, "n": n,
    }


def main() -> None:
    df = load_uf_data()
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    print("Variáveis selecionadas (27 UFs):")
    print(df[["uf", TARGET, *FEATURES]].round(4).to_string(index=False))

    print("\nMatriz de correlação dos preditores:")
    print(df[FEATURES].corr().round(3))

    X = df[FEATURES].to_numpy(dtype=float)
    y = df[TARGET].to_numpy(dtype=float)
    res = fit_ols(X, y)

    print(f"\n{'='*70}")
    print(f"OLS — Y = {TARGET}")
    print(f"N = {res['n']}, df residual = {res['df_resid']}")
    print(f"R² = {res['r2']:.4f}   R²_adj = {res['r2_adj']:.4f}   F = {res['f']:.3f}")
    print(f"{'='*70}")
    names = ["(Intercepto)", *FEATURES]
    print(f"{'Variável':<25}{'Coef':>14}{'Std.Err':>14}{'t':>10}")
    for n, b, s, t in zip(names, res["beta"], res["se"], res["t"]):
        print(f"{n:<25}{b:>14.4f}{s:>14.4f}{t:>10.3f}")

    print("\nResíduos (acid por 1000 hab — observado vs estimado):")
    out = df[["uf"]].copy()
    out["y_obs"] = y.round(3)
    out["y_pred"] = res["y_hat"].round(3)
    out["residuo"] = res["residuos"].round(3)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
