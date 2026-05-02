"""Tela tkinter — Simulador de acidentes do trabalho.

- Aba "Simulador": sliders para cada indicador; a taxa estimada de acidentes
  recalcula em tempo real conforme você mexe.
- Aba "Análise": os 4 gráficos diagnósticos do modelo.
- Botão "Exportar PDF": gera o relatório completo.

Roda com: python app/gui.py
"""

from __future__ import annotations

import datetime as _dt
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from dependencies.load_data import load_uf_data
from main import FEATURES, TARGET, fit_ols


VAR_INFO: dict[str, tuple[str, str, str]] = {
    # var: (rótulo curto, unidade/escala, descrição)
    "acid_por_mil_hab_2023": (
        "Taxa de acidentes (CAT) por 1.000 hab.",
        "por 1.000 habitantes",
        "Quantidade de acidentes do trabalho com CAT registrada (DATAPREV/MPS) "
        "dividida pela população residente estimada (IBGE 2024). É a variável Y.",
    ),
    "idhm_2021": (
        "IDHM",
        "0 a 1",
        "Índice de Desenvolvimento Humano Municipal (geral) — combina renda, "
        "longevidade e educação. Maior = mais desenvolvido. Fonte: PNUD/IPEA/FJP, 2021.",
    ),
    "gini_2023": (
        "Gini",
        "0 a 1",
        "Coeficiente de Gini do rendimento mensal real domiciliar per capita. "
        "0 = igualdade total; 1 = desigualdade máxima. Fonte: IBGE PNAD-C 2023.",
    ),
    "pct_industria": (
        "% Indústria no VAB",
        "fração 0 a 1",
        "Participação da indústria no Valor Adicionado Bruto da UF. "
        "Fonte: IBGE Contas Regionais 2021.",
    ),
    "pib_per_capita_2021": (
        "PIB per capita",
        "mil R$",
        "PIB total / população, em milhares de reais correntes. "
        "Fonte: IBGE Contas Regionais 2021 + Estimativas de população.",
    ),
}

SLIDER_RANGES: dict[str, tuple[float, float, float]] = {
    # var: (min, max, step)
    "idhm_2021": (0.65, 0.85, 0.001),
    "gini_2023": (0.40, 0.60, 0.001),
    "pct_industria": (0.00, 0.55, 0.005),
    "pib_per_capita_2021": (10.0, 110.0, 0.5),
}


PLOT_DESCRIPTIONS = {
    "Observado vs Estimado": (
        "Cada ponto é uma UF. Eixo X: taxa real. Eixo Y: taxa que o modelo prevê. "
        "Linha tracejada y=x = ajuste perfeito. Quanto mais próximo da linha, melhor."
    ),
    "Resíduos por UF": (
        "Resíduo = observado − estimado. Verde = modelo subestimou (realidade > previsão). "
        "Vermelho = modelo superestimou. UFs com resíduo grande têm fatores não capturados."
    ),
    "Coeficientes": (
        "Cada barra é o efeito ajustado de uma variável (mantendo as outras fixas). "
        "Barra de erro = IC 95% (±1,96·SE). Barra que não cruza zero → significativo."
    ),
    "Scatter Y vs preditor": (
        "Relação bivariada entre o preditor e a taxa. Linha tracejada = ajuste linear simples. "
        "Atenção: NÃO controla pelos outros preditores. Para o efeito ajustado, use 'Coeficientes'."
    ),
}
ANALYSIS_OPTIONS = tuple(PLOT_DESCRIPTIONS.keys())


def feature_short(feat: str) -> str:
    return VAR_INFO[feat][0] if feat in VAR_INFO else feat


def feature_unit(feat: str) -> str:
    return VAR_INFO[feat][1] if feat in VAR_INFO else ""


def fmt_p_indicator(t: float) -> str:
    if abs(t) > 2.83:
        return "***"
    if abs(t) > 2.07:
        return "*"
    if abs(t) > 1.72:
        return "."
    return ""


# ------------------ Simulador ------------------


class SimulatorTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, df: pd.DataFrame, res: dict):
        super().__init__(parent, padding=12)
        self.df = df
        self.res = res
        self.beta = res["beta"]
        self.sliders: dict[str, tk.DoubleVar] = {}
        self.value_labels: dict[str, ttk.Label] = {}
        self._build()
        self._refresh()

    def _build(self) -> None:
        # ---- Coluna esquerda: sliders + resultado
        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        left.columnconfigure(0, weight=1)

        ttk.Label(
            left, text="Mexa nos indicadores",
            font=("Segoe UI", 13, "bold"), foreground="#1a3d6c",
        ).pack(anchor=tk.W)
        ttk.Label(
            left,
            text="A taxa estimada de acidentes recalcula em tempo real.",
            foreground="#555",
        ).pack(anchor=tk.W, pady=(0, 12))

        for feat in FEATURES:
            self._build_slider(left, feat)

        ttk.Button(
            left, text="↻ Resetar para a média do Brasil",
            command=self._reset_to_means,
        ).pack(anchor=tk.W, pady=(8, 0))

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=14)

        # Resultado: número grande
        result_frame = ttk.Frame(left)
        result_frame.pack(fill=tk.X)
        ttk.Label(
            result_frame, text="Taxa estimada de acidentes",
            font=("Segoe UI", 10), foreground="#555",
        ).pack(anchor=tk.W)
        self.result_var = tk.StringVar(value="0,00")
        ttk.Label(
            result_frame, textvariable=self.result_var,
            font=("Segoe UI", 38, "bold"), foreground="#1a3d6c",
        ).pack(anchor=tk.W)
        ttk.Label(
            result_frame, text="acidentes (CAT) por 1.000 habitantes/ano",
            font=("Segoe UI", 10), foreground="#555",
        ).pack(anchor=tk.W)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=14)

        # Comparativo: UF mais próxima do cenário
        ttk.Label(
            left, text="UF mais parecida com este cenário",
            font=("Segoe UI", 10, "bold"), foreground="#1a3d6c",
        ).pack(anchor=tk.W)
        self.match_var = tk.StringVar(value="—")
        ttk.Label(
            left, textvariable=self.match_var,
            font=("Consolas", 10), wraplength=320, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 0))

        # ---- Coluna direita: gráficos de dependência parcial
        right = ttk.Frame(self)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(
            right,
            text="Como a taxa muda quando você move um slider",
            font=("Segoe UI", 11, "bold"), foreground="#1a3d6c",
        ).pack(anchor=tk.W)
        ttk.Label(
            right,
            text=("Cada gráfico fixa os outros indicadores no valor atual e varia somente o do título. "
                  "Pontos cinza = UFs reais. Linha azul = previsão do modelo. "
                  "Ponto vermelho = seu cenário atual."),
            foreground="#555", wraplength=720, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 6))

        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.axes = {}
        rows, cols = 2, 2
        for i, feat in enumerate(FEATURES):
            ax = self.fig.add_subplot(rows, cols, i + 1)
            self.axes[feat] = ax
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _build_slider(self, parent: ttk.Frame, feat: str) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(8, 0))
        frame.columnconfigure(0, weight=1)

        title = ttk.Label(
            frame, text=feature_short(feat),
            font=("Segoe UI", 10, "bold"),
        )
        title.grid(row=0, column=0, sticky=tk.W)

        unit = ttk.Label(
            frame, text=f"({feature_unit(feat)})",
            font=("Segoe UI", 8), foreground="#888",
        )
        unit.grid(row=0, column=1, sticky=tk.E)

        var = tk.DoubleVar(value=float(self.df[feat].mean()))
        self.sliders[feat] = var

        lo, hi, step = SLIDER_RANGES[feat]
        scale = ttk.Scale(
            frame, from_=lo, to=hi, orient=tk.HORIZONTAL,
            variable=var, length=320,
            command=lambda _v: self._refresh(),
        )
        scale.grid(row=1, column=0, columnspan=2, sticky=tk.EW)

        bottom = ttk.Frame(frame)
        bottom.grid(row=2, column=0, columnspan=2, sticky=tk.EW)
        ttk.Label(bottom, text=f"min {lo:g}", foreground="#888", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        value_lbl = ttk.Label(bottom, text="", font=("Consolas", 10, "bold"), foreground="#1a3d6c")
        value_lbl.pack(side=tk.LEFT, expand=True)
        ttk.Label(bottom, text=f"max {hi:g}", foreground="#888", font=("Segoe UI", 8)).pack(side=tk.RIGHT)
        self.value_labels[feat] = value_lbl

    def _reset_to_means(self) -> None:
        for feat in FEATURES:
            self.sliders[feat].set(float(self.df[feat].mean()))
        self._refresh()

    def _predict(self, x: np.ndarray) -> float:
        return float(self.beta[0] + np.dot(self.beta[1:], x))

    def _current_x(self) -> np.ndarray:
        return np.array([self.sliders[f].get() for f in FEATURES])

    def _refresh(self) -> None:
        x = self._current_x()
        y_pred = max(0.0, self._predict(x))
        self.result_var.set(f"{y_pred:.2f}".replace(".", ","))

        for feat, val in zip(FEATURES, x):
            decimals = 3 if SLIDER_RANGES[feat][2] < 0.01 else 2
            self.value_labels[feat].config(text=f"= {val:.{decimals}f}")

        # UF mais próxima (distância normalizada nos preditores)
        sd = self.df[FEATURES].std().to_numpy()
        d = ((self.df[FEATURES].to_numpy() - x) / sd) ** 2
        idx = int(np.argsort(d.sum(axis=1))[0])
        row = self.df.iloc[idx]
        self.match_var.set(
            f"{row['uf']} — {row['uf_nome']}\n"
            f"taxa real: {row[TARGET]:.2f} por 1.000 hab."
        )

        # Gráficos de dependência parcial
        for feat in FEATURES:
            ax = self.axes[feat]
            ax.clear()
            lo, hi, _ = SLIDER_RANGES[feat]
            xs = np.linspace(lo, hi, 80)
            i = FEATURES.index(feat)
            base = x.copy()
            preds = []
            for v in xs:
                base[i] = v
                preds.append(max(0.0, self._predict(base)))
            preds = np.array(preds)

            ax.scatter(self.df[feat], self.df[TARGET], color="#bbbbbb", s=18, label="UFs reais")
            ax.plot(xs, preds, color="#1f77b4", linewidth=2, label="previsão")
            ax.axvline(x[i], color="#777", linestyle=":", linewidth=1)
            ax.scatter([x[i]], [y_pred], color="#d62728", s=70, zorder=5,
                       edgecolor="white", linewidth=1.5, label="cenário")
            ax.set_title(feature_short(feat), fontsize=10)
            ax.set_ylabel("acid./1.000 hab.", fontsize=8)
            ax.set_xlabel(feature_unit(feat), fontsize=8)
            ax.tick_params(axis="both", labelsize=8)
            ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw_idle()


# ------------------ Análise estatística ------------------


class AnalysisTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, df: pd.DataFrame, res: dict):
        super().__init__(parent, padding=12)
        self.df = df
        self.res = res
        self._build()
        self._draw()

    def _build(self) -> None:
        side = ttk.Frame(self)
        side.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))

        ttk.Label(side, text="Visualização", font=("Segoe UI", 10, "bold"), foreground="#1a3d6c").pack(anchor=tk.W)
        self.choice = tk.StringVar(value=ANALYSIS_OPTIONS[0])
        cb = ttk.Combobox(side, textvariable=self.choice, values=ANALYSIS_OPTIONS, state="readonly", width=30)
        cb.pack(anchor=tk.W, pady=(2, 8))
        cb.bind("<<ComboboxSelected>>", lambda _e: self._draw())

        ttk.Label(side, text="Preditor (para scatter)", font=("Segoe UI", 10, "bold"), foreground="#1a3d6c").pack(anchor=tk.W)
        self.feat = tk.StringVar(value=FEATURES[0])
        cb2 = ttk.Combobox(side, textvariable=self.feat, values=FEATURES, state="readonly", width=30)
        cb2.pack(anchor=tk.W, pady=(2, 12))
        cb2.bind("<<ComboboxSelected>>", lambda _e: self._draw())

        ttk.Separator(side, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)
        ttk.Label(side, text="Estatísticas", font=("Segoe UI", 10, "bold"), foreground="#1a3d6c").pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            side,
            text=(
                f"  N = {self.res['n']}\n"
                f"  gl = {self.res['df_resid']}\n"
                f"  R² = {self.res['r2']:.4f}\n"
                f"  R²_adj = {self.res['r2_adj']:.4f}\n"
                f"  F = {self.res['f']:.3f}"
            ),
            font=("Consolas", 10), justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 8))

        ttk.Label(side, text="Coeficientes", font=("Segoe UI", 10, "bold"), foreground="#1a3d6c").pack(anchor=tk.W)
        box = tk.Text(side, width=38, height=8, font=("Consolas", 9),
                      bg="#f8f9fa", relief=tk.FLAT, borderwidth=1, highlightthickness=1, highlightbackground="#ccc")
        box.pack(fill=tk.X, pady=(2, 4))
        box.insert(tk.END, f"{'Var':<20}{'β':>8}{'t':>6} sig\n" + "-" * 38 + "\n")
        for n, b, t in zip(["(Intercepto)", *FEATURES], self.res["beta"], self.res["t"]):
            short = feature_short(n) if n in VAR_INFO else n[:20]
            box.insert(tk.END, f"{short:<20}{b:>8.3f}{t:>6.2f} {fmt_p_indicator(t)}\n")
        box.config(state=tk.DISABLED)
        ttk.Label(side, text="*** p<0,01    * p<0,05    . p<0,10",
                  font=("Segoe UI", 8), foreground="#888").pack(anchor=tk.W)

        right = ttk.Frame(self)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        desc_frame = ttk.LabelFrame(right, text=" Como ler ", padding=10)
        desc_frame.pack(fill=tk.X, pady=(0, 6))
        self.desc = ttk.Label(desc_frame, text="", wraplength=720, justify=tk.LEFT)
        self.desc.pack(anchor=tk.W, fill=tk.X)

        self.fig = Figure(figsize=(8, 5.4), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = ttk.Frame(right)
        toolbar.pack(fill=tk.X)
        NavigationToolbar2Tk(self.canvas, toolbar).update()

    def _draw(self) -> None:
        choice = self.choice.get()
        self.desc.config(text=PLOT_DESCRIPTIONS[choice])
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        plot_into(ax, choice, self.feat.get(), self.df, self.res)
        self.fig.tight_layout()
        self.canvas.draw_idle()


def plot_into(ax, choice: str, feat: str, df: pd.DataFrame, res: dict) -> None:
    ufs = df["uf"].tolist()
    if choice == "Observado vs Estimado":
        y = df[TARGET].to_numpy()
        yh = res["y_hat"]
        ax.scatter(y, yh, color="#1f77b4", s=40, edgecolor="white")
        for u, a, b in zip(ufs, y, yh):
            ax.annotate(u, (a, b), textcoords="offset points", xytext=(5, 5), fontsize=8)
        lim = [min(y.min(), yh.min()) - 0.3, max(y.max(), yh.max()) + 0.3]
        ax.plot(lim, lim, "--", color="gray", linewidth=1, label="y = x")
        ax.set_xlabel("Taxa observada (CAT/1.000 hab.)")
        ax.set_ylabel("Taxa estimada")
        ax.set_title("Observado vs Estimado")
        ax.legend(loc="upper left", fontsize=9)

    elif choice == "Resíduos por UF":
        order = np.argsort(res["residuos"])
        colors = ["#d62728" if r < 0 else "#2ca02c" for r in res["residuos"][order]]
        ax.barh(np.array(ufs)[order], res["residuos"][order], color=colors, edgecolor="black", linewidth=0.4)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Resíduo (obs − estim)")
        ax.set_title("Resíduos por UF — verde: subestimou; vermelho: superestimou")

    elif choice == "Coeficientes":
        names = ["(Intercepto)", *[feature_short(f) for f in FEATURES]]
        beta = res["beta"]
        se = res["se"]
        colors = ["#2ca02c" if abs(t) > 2.07 else "#999999" for t in res["t"]]
        ax.barh(names, beta, xerr=1.96 * se, color=colors, edgecolor="black", linewidth=0.5,
                error_kw={"ecolor": "#444", "capsize": 4})
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Coeficiente (IC 95%)")
        ax.set_title("Coeficientes — verde: significativo (p<0,05)")

    else:  # Scatter Y vs preditor
        x = df[feat].to_numpy()
        y = df[TARGET].to_numpy()
        ax.scatter(x, y, color="#1f77b4", s=40, edgecolor="white")
        for u, a, b in zip(ufs, x, y):
            ax.annotate(u, (a, b), textcoords="offset points", xytext=(5, 5), fontsize=8)
        slope, intercept = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 50)
        ax.plot(xs, slope * xs + intercept, "--", color="gray", linewidth=1)
        r = np.corrcoef(x, y)[0, 1]
        ax.set_xlabel(feature_short(feat))
        ax.set_ylabel(feature_short(TARGET))
        ax.set_title(f"Y vs {feature_short(feat)}  (r = {r:.3f})")
    ax.grid(True, alpha=0.3)


# ------------------ App principal ------------------


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Simulador — Acidentes do trabalho × variáveis socioeconômicas")
        self.geometry("1300x820")
        self.minsize(1100, 700)

        self.df = load_uf_data().sort_values("uf").reset_index(drop=True)
        X = self.df[FEATURES].to_numpy(dtype=float)
        y = self.df[TARGET].to_numpy(dtype=float)
        self.res = fit_ols(X, y)

        self._setup_style()

        # header
        header = ttk.Frame(self, padding=(16, 10))
        header.pack(fill=tk.X)
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text="Simulador de acidentes do trabalho",
            font=("Segoe UI", 14, "bold"), foreground="#1a3d6c",
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            header,
            text="Modelo de regressão linear múltipla com 27 UFs do Brasil",
            font=("Segoe UI", 9), foreground="#555",
        ).grid(row=1, column=0, sticky=tk.W)

        ttk.Button(header, text="📄 Exportar PDF", command=self._export_pdf).grid(row=0, column=1, rowspan=2, sticky=tk.E, padx=4)
        ttk.Button(header, text="ℹ Glossário", command=self._show_glossary).grid(row=0, column=2, rowspan=2, sticky=tk.E)

        ttk.Separator(self).pack(fill=tk.X)

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.simulator = SimulatorTab(notebook, self.df, self.res)
        self.analysis = AnalysisTab(notebook, self.df, self.res)
        notebook.add(self.simulator, text="🎚  Simulador")
        notebook.add(self.analysis, text="📊  Análise estatística")

        self.status = tk.StringVar(value="Pronto.")
        bar = ttk.Frame(self, padding=(8, 4))
        bar.pack(fill=tk.X)
        ttk.Label(bar, textvariable=self.status, font=("Segoe UI", 9), foreground="#555").pack(side=tk.LEFT)
        ttk.Label(bar, text="Fontes: IBGE · DATAPREV/MPS · PNUD/IPEA",
                  font=("Segoe UI", 9), foreground="#555").pack(side=tk.RIGHT)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("clam")

    def _show_glossary(self) -> None:
        win = tk.Toplevel(self)
        win.title("Glossário")
        win.geometry("680x520")
        win.transient(self)
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="O que cada indicador significa",
                  font=("Segoe UI", 13, "bold"), foreground="#1a3d6c").pack(anchor=tk.W)
        text = tk.Text(frame, wrap=tk.WORD, font=("Segoe UI", 10), borderwidth=1, relief=tk.SOLID)
        text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        text.tag_configure("title", font=("Segoe UI", 10, "bold"), foreground="#1a3d6c", spacing3=4)
        text.tag_configure("body", font=("Segoe UI", 10), spacing3=10)
        for var, (title, unit, desc) in VAR_INFO.items():
            text.insert(tk.END, f"{title}  ({unit})\n", "title")
            text.insert(tk.END, f"{desc}\n\n", "body")
        text.config(state=tk.DISABLED)
        ttk.Button(frame, text="Fechar", command=win.destroy).pack(anchor=tk.E, pady=(8, 0))

    def _export_pdf(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Salvar relatório PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"relatorio_acidentes_{_dt.date.today():%Y-%m-%d}.pdf",
        )
        if not path:
            return
        try:
            self.status.set("Gerando PDF...")
            self.update_idletasks()
            self._write_pdf(Path(path))
            self.status.set(f"Relatório salvo: {path}")
            messagebox.showinfo("PDF gerado", f"Salvo em:\n{path}")
        except Exception as exc:
            self.status.set("Erro ao gerar PDF.")
            messagebox.showerror("Erro", f"Não foi possível gerar:\n{exc}")

    def _write_pdf(self, path: Path) -> None:
        with PdfPages(path) as pdf:
            self._pdf_cover(pdf)
            self._pdf_simulator_snapshot(pdf)
            for choice in list(PLOT_DESCRIPTIONS.keys())[:3]:
                fig = Figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                plot_into(ax, choice, FEATURES[0], self.df, self.res)
                fig.suptitle(choice, fontsize=14, fontweight="bold", y=0.98)
                fig.text(0.07, 0.04, PLOT_DESCRIPTIONS[choice], wrap=True, fontsize=9, color="#333")
                fig.tight_layout(rect=[0.05, 0.08, 0.97, 0.94])
                pdf.savefig(fig)
            for feat in FEATURES:
                fig = Figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                plot_into(ax, "Scatter Y vs preditor", feat, self.df, self.res)
                fig.suptitle(f"Scatter: {feature_short(feat)}", fontsize=14, fontweight="bold", y=0.98)
                fig.text(0.07, 0.04, PLOT_DESCRIPTIONS["Scatter Y vs preditor"],
                         wrap=True, fontsize=9, color="#333")
                fig.tight_layout(rect=[0.05, 0.08, 0.97, 0.94])
                pdf.savefig(fig)

    def _pdf_simulator_snapshot(self, pdf: PdfPages) -> None:
        x = np.array([self.simulator.sliders[f].get() for f in FEATURES])
        y_pred = max(0.0, float(self.res["beta"][0] + np.dot(self.res["beta"][1:], x)))

        fig = Figure(figsize=(11, 8.5))
        fig.suptitle("Cenário simulado", fontsize=14, fontweight="bold", y=0.98)

        # Resumo na parte de cima
        text = (
            f"Cenário atual:\n"
            + "\n".join(f"  • {feature_short(f):<28} = {v:.3f}  ({feature_unit(f)})" for f, v in zip(FEATURES, x))
            + f"\n\nTaxa estimada de acidentes: {y_pred:.2f} por 1.000 habitantes/ano"
        )
        fig.text(0.07, 0.78, text, fontsize=10, family="monospace", verticalalignment="top")

        # Mini-gráficos
        for i, feat in enumerate(FEATURES):
            ax = fig.add_subplot(2, 2, i + 1)
            ax.set_position([0.10 + 0.45 * (i % 2), 0.08 + 0.30 * (1 - i // 2), 0.38, 0.28])
            lo, hi, _ = SLIDER_RANGES[feat]
            xs = np.linspace(lo, hi, 80)
            base = x.copy()
            preds = []
            for v in xs:
                base[FEATURES.index(feat)] = v
                preds.append(max(0.0, float(self.res["beta"][0] + np.dot(self.res["beta"][1:], base))))
            ax.scatter(self.df[feat], self.df[TARGET], color="#bbb", s=14)
            ax.plot(xs, preds, color="#1f77b4")
            ax.axvline(x[FEATURES.index(feat)], color="#777", linestyle=":", linewidth=1)
            ax.scatter([x[FEATURES.index(feat)]], [y_pred], color="#d62728", s=50, zorder=5)
            ax.set_title(feature_short(feat), fontsize=10)
            ax.set_xlabel(feature_unit(feat), fontsize=8)
            ax.set_ylabel("acid./1000 hab.", fontsize=8)
            ax.tick_params(axis="both", labelsize=7)
            ax.grid(True, alpha=0.3)
        pdf.savefig(fig)

    def _pdf_cover(self, pdf: PdfPages) -> None:
        fig = Figure(figsize=(11, 8.5))
        fig.patch.set_facecolor("white")
        fig.text(0.07, 0.92, "Relatório — Simulador de acidentes do trabalho",
                 fontsize=20, fontweight="bold", color="#1a3d6c")
        fig.text(0.07, 0.88, "Regressão linear múltipla — 27 UFs do Brasil",
                 fontsize=12, color="#444")
        fig.text(0.07, 0.85, f"Gerado em: {_dt.date.today():%d/%m/%Y}",
                 fontsize=10, color="#777")

        fig.text(0.07, 0.78, "Modelo", fontsize=13, fontweight="bold", color="#1a3d6c")
        fig.text(0.07, 0.73,
                 f"Y = {feature_short(TARGET)} ({feature_unit(TARGET)})\n"
                 f"X = " + ", ".join(feature_short(f) for f in FEATURES),
                 fontsize=10)

        fig.text(0.07, 0.66, "Estatísticas", fontsize=13, fontweight="bold", color="#1a3d6c")
        fig.text(0.07, 0.58,
                 f"N = {self.res['n']}     gl residual = {self.res['df_resid']}\n"
                 f"R² = {self.res['r2']:.4f}     R² ajustado = {self.res['r2_adj']:.4f}\n"
                 f"F = {self.res['f']:.3f}",
                 fontsize=10, family="monospace")

        fig.text(0.07, 0.50, "Coeficientes", fontsize=13, fontweight="bold", color="#1a3d6c")
        lines = [f"{'Variável':<26}{'β':>10}{'SE':>10}{'t':>8}  sig"]
        for n, b, s, t in zip(["(Intercepto)", *FEATURES], self.res["beta"], self.res["se"], self.res["t"]):
            short = feature_short(n) if n in VAR_INFO else (n if n == "(Intercepto)" else n[:26])
            lines.append(f"{short:<26}{b:>10.3f}{s:>10.3f}{t:>8.2f}  {fmt_p_indicator(t)}")
        fig.text(0.07, 0.30, "\n".join(lines), fontsize=9, family="monospace")
        fig.text(0.07, 0.26, "*** p<0,01    * p<0,05    . p<0,10", fontsize=8, color="#666")

        fig.text(0.07, 0.18, "Fontes", fontsize=13, fontweight="bold", color="#1a3d6c")
        fig.text(0.07, 0.10,
                 "• Acidentes (CAT) por UF — AEAT 2023, DATAPREV/MPS\n"
                 "• População — IBGE Estimativas 2024\n"
                 "• PIB e VAB — IBGE Contas Regionais 2021\n"
                 "• IDHM — PNUD/IPEA/FJP 2021\n"
                 "• Gini — IBGE PNAD-C 2023",
                 fontsize=9, color="#333")
        pdf.savefig(fig)


if __name__ == "__main__":
    App().mainloop()
