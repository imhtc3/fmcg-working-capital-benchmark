"""Working-capital and liquidity benchmark for 9 listed Indian FMCG companies, FY2015-FY2025.

Answers three treasury questions:
  1. How long is each company's cash conversion cycle (CCC) and how has it moved?
  2. How much cash would each company release if it matched the peer median on each lever?
  3. Which cash-management / trade-finance product fits each lever?

Run:  python analysis.py      (writes to outputs/)
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
YEARS = [f"FY{y}" for y in range(2015, 2026)]
LATEST, BASE = "FY2025", "FY2015"

# Product each lever maps to in a bank's cash-management / trade-finance offering
PRODUCT = {
    "debtor_days": "Receivables: collections, virtual accounts, receivables finance",
    "inventory_days": "Inventory: inventory / distributor finance",
    "payable_days": "Payables: supply chain finance, extended payment terms",
}


def load() -> pd.DataFrame:
    raw = pd.read_csv(ROOT / "data" / "raw_fmcg_working_capital.csv")
    long = raw.melt(id_vars=["company", "ticker", "basis", "metric"], value_vars=YEARS,
                    var_name="year", value_name="value")
    return long.pivot_table(index=["ticker", "company", "year"], columns="metric",
                            values="value").reset_index()


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """CCC must equal debtor + inventory - payable days (allow 2 days for rounding)."""
    df["ccc"] = df.debtor_days + df.inventory_days - df.payable_days
    df["ccc_gap"] = (df.ccc - df.ccc_reported).abs()
    bad = df[df.ccc_gap > 2]
    if len(bad):
        raise ValueError(f"CCC identity fails for:\n{bad[['ticker','year','ccc','ccc_reported']]}")
    print(f"Validation passed: {len(df)} company-years, max rounding gap {df.ccc_gap.max():.0f} day(s)")
    return df


def cash_release(df: pd.DataFrame) -> pd.DataFrame:
    """Cash tied up and the cash each company frees by reaching the peer median on each lever.

    Days are converted to rupees with sales/365 (one day of sales), so every figure is an
    approximation on a sales base.
    """
    cur = df[df.year == LATEST].copy()
    cur["one_day_sales_cr"] = cur.sales_cr / 365
    cur["cash_tied_up_cr"] = cur.ccc * cur.one_day_sales_cr
    for lever in PRODUCT:
        med = cur[lever].median()
        # worse than median = more receivable/inventory days, or fewer payable days
        gap = (cur[lever] - med) if lever != "payable_days" else (med - cur[lever])
        cur[f"{lever}_median"] = med
        cur[f"{lever}_release_cr"] = gap.clip(lower=0) * cur.one_day_sales_cr
    rel = [f"{l}_release_cr" for l in PRODUCT]
    cur["total_release_cr"] = cur[rel].sum(axis=1)
    cur["biggest_lever"] = cur[rel].idxmax(axis=1).str.replace("_release_cr", "")
    cur.loc[cur.total_release_cr == 0, "biggest_lever"] = "none"
    cur["recommended_product"] = cur.biggest_lever.map(PRODUCT).fillna("At or better than peer median")
    return cur.sort_values("total_release_cr", ascending=False)


def trend(df: pd.DataFrame) -> pd.DataFrame:
    w = df.pivot(index="ticker", columns="year", values="ccc")
    s = df[df.year == LATEST].set_index("ticker").sales_cr
    t = pd.DataFrame({"ccc_FY2015": w[BASE], "ccc_FY2025": w[LATEST]})
    t["change_days"] = t.ccc_FY2025 - t.ccc_FY2015
    # cash freed (+) or absorbed (-) by the change, valued at FY2025 sales
    t["cash_effect_cr"] = -t.change_days * s / 365
    return t.sort_values("change_days")


def scfin_scenario(cur: pd.DataFrame, extra_days: int = 15) -> pd.DataFrame:
    """Supply chain finance: suppliers get paid early by the bank, buyer pays the bank later."""
    s = cur.set_index("ticker")
    return pd.DataFrame({
        "payable_days_now": s.payable_days,
        "payable_days_with_scf": s.payable_days + extra_days,
        "cash_released_cr": extra_days * s.one_day_sales_cr,
    }).sort_values("cash_released_cr", ascending=False)


def charts(df: pd.DataFrame, cur: pd.DataFrame) -> None:
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    # 1. CCC trend for the peer set, highlighting the biggest movers
    fig, ax = plt.subplots(figsize=(9, 5))
    w = df.pivot(index="year", columns="ticker", values="ccc").loc[YEARS]
    for t in w.columns:
        hi = t in ("ITC", "TATACONSUM", "HINDUNILVR")
        ax.plot(range(len(YEARS)), w[t], lw=2.4 if hi else 1, alpha=1 if hi else .35,
                label=t if hi else None)
    ax.plot(range(len(YEARS)), w.median(axis=1), "k--", lw=1.5, label="Peer median")
    ax.axhline(0, color="grey", lw=.6)
    ax.set_xticks(range(len(YEARS)), [y[2:] for y in YEARS])
    ax.set_ylabel("Cash conversion cycle (days)")
    ax.set_title("Cash conversion cycle, 9 Indian FMCG companies")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "ccc_trend.png", dpi=150); plt.close(fig)

    # 2. Cash release opportunity by lever, FY2025
    fig, ax = plt.subplots(figsize=(9, 5))
    # ITC is excluded: its leaf-tobacco stock is aged for years by design, so a peer median is not a fair target
    c = cur[(cur.total_release_cr > 0) & (cur.ticker != "ITC")].set_index("ticker")
    left = pd.Series(0.0, index=c.index)
    for lever, col in zip(PRODUCT, ["#1F3A5F", "#7A9CC6", "#C9A227"]):
        v = c[f"{lever}_release_cr"]
        ax.barh(c.index, v, left=left, color=col, label=lever.replace("_", " ").title())
        left += v
    ax.invert_yaxis()
    ax.set_xlabel("Cash released by reaching peer median (Rs crore)")
    ax.set_title(f"Working-capital cash release opportunity, {LATEST} (excl. ITC)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "cash_release.png", dpi=150); plt.close(fig)


def main() -> None:
    df = validate(load())
    cur = cash_release(df)
    tr = trend(df)
    scf = scfin_scenario(cur)
    charts(df, cur)

    cols = ["company", "sales_cr", "debtor_days", "inventory_days", "payable_days", "ccc",
            "cash_tied_up_cr", "debtor_days_release_cr", "inventory_days_release_cr",
            "payable_days_release_cr", "total_release_cr", "recommended_product"]
    cur[cols].round(0).to_csv(OUT / "fy2025_cash_release.csv", index=False)
    tr.round(0).to_csv(OUT / "ccc_trend_FY2015_FY2025.csv")
    scf.round(0).to_csv(OUT / "supply_chain_finance_scenario.csv")
    df.to_csv(OUT / "clean_panel.csv", index=False)

    pd.set_option("display.width", 200)
    print("\nPeer medians FY2025:",
          {l: cur[l].median() for l in PRODUCT}, "CCC:", cur.ccc.median())
    print("\n", cur[cols].round(0).to_string(index=False))
    print("\nTotal release opportunity (Rs cr):", round(cur.total_release_cr.sum()),
          "| excl. ITC:", round(cur[cur.ticker != "ITC"].total_release_cr.sum()))
    print("\n", tr.round(0).to_string())
    print("\nSCF +15 days, total (Rs cr):", round(scf.cash_released_cr.sum()))
    print(scf.round(0).to_string())


if __name__ == "__main__":
    main()
