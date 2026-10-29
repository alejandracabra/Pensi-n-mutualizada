"""Paleta SURA solicitada para gráficos y reportes del proyecto."""

import plotly.graph_objects as go
import plotly.io as pio

SURA_PRIMARY = "#0033A0"
SURA_SECONDARY = "#00AEC7"
SURA_LIGHT = "#FFFFFF"
SURA_DARK = "#0033A0"
SURA_ACCENT = "#4EC3E0"
SURA_LIME = "#E3E829"
SURA_YELLOW = "#FFE946"
SURA_FONT_FAMILY = '"Sura Sans", Arial, sans-serif'
SURA_PLOTLY_FONT = "Sura Sans, Arial, sans-serif"

SURA_PALETTE = (
    SURA_PRIMARY,
    SURA_SECONDARY,
    SURA_ACCENT,
    SURA_LIME,
    SURA_YELLOW,
)

pio.templates["sura"] = go.layout.Template(
    layout={
        "colorway": list(SURA_PALETTE),
        "font": {"color": SURA_DARK, "family": SURA_PLOTLY_FONT},
        "paper_bgcolor": SURA_LIGHT,
        "plot_bgcolor": SURA_LIGHT,
        "title": {"font": {"color": SURA_PRIMARY}},
        "legend": {"font": {"color": SURA_DARK}},
        "xaxis": {
            "color": SURA_DARK,
            "gridcolor": "rgba(78,195,224,0.24)",
            "linecolor": SURA_SECONDARY,
            "zerolinecolor": SURA_ACCENT,
        },
        "yaxis": {
            "color": SURA_DARK,
            "gridcolor": "rgba(78,195,224,0.24)",
            "linecolor": SURA_SECONDARY,
            "zerolinecolor": SURA_ACCENT,
        },
    }
)

PLOTLY_TEMPLATE = "sura"
