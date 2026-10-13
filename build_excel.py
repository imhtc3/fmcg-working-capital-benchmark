"""Build the Excel working-capital model. Every output cell is a live formula on the Inputs sheet."""
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).parent
panel = pd.read_csv(ROOT / "outputs" / "clean_panel.csv")
cur = panel[panel.year == "FY2025"].sort_values("sales_cr", ascending=False).reset_index(drop=True)
n = len(cur)
first, last = 5, 5 + n - 1  # data rows

NAVY = "1F3A5F"
HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor=NAVY)
INPUT = Font(color="0000FF")  # blue = hard-coded input, black = formula
TITLE = Font(bold=True, size=14, color=NAVY)


def header(ws, row, cols):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font, cell.fill = HEAD, FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[row].height = 32


wb = Workbook()

# ---- Inputs ----
ws = wb.active
ws.title = "Inputs"
ws["A1"], ws["A1"].font = "FY2025 working-capital inputs (blue = source data)", TITLE
ws["A2"] = "Source: Screener.in ratios tables (consolidated; Britannia and Colgate standalone). Sales in Rs crore."
header(ws, 4, ["Company", "Ticker", "Sales (Rs cr)", "Debtor days", "Inventory days", "Payable days"])
for i, r in cur.iterrows():
    row = first + i
    for col, v in enumerate([r.company, r.ticker, r.sales_cr, r.debtor_days, r.inventory_days, r.payable_days], 1):
        c = ws.cell(row=row, column=col, value=v)
        if col >= 3:
            c.font = INPUT
for col, w in zip("ABCDEF", [28, 13, 14, 12, 14, 13]):
    ws.column_dimensions[col].width = w

# ---- Model ----
m = wb.create_sheet("Model")
m["A1"], m["A1"].font = "Cash conversion cycle and cash release to peer median", TITLE
m["A2"] = "Cash per day = Sales / 365. Release = days worse than peer median x cash per day (0 if already better)."
cols = ["Company", "Cash per day (Rs cr)", "CCC (days)", "Cash tied up (Rs cr)",
        "Release: receivables", "Release: inventory", "Release: payables", "Total release (Rs cr)", "Biggest lever"]
header(m, 4, cols)
I = "Inputs!"
for k in range(n):
    r = first + k
    m[f"A{r}"] = f"={I}A{r}"
    m[f"B{r}"] = f"={I}C{r}/365"
    m[f"C{r}"] = f"={I}D{r}+{I}E{r}-{I}F{r}"
    m[f"D{r}"] = f"=C{r}*B{r}"
    m[f"E{r}"] = f"=MAX(0,{I}D{r}-MEDIAN({I}D${first}:{I}D${last}))*B{r}"
    m[f"F{r}"] = f"=MAX(0,{I}E{r}-MEDIAN({I}E${first}:{I}E${last}))*B{r}"
    m[f"G{r}"] = f"=MAX(0,MEDIAN({I}F${first}:{I}F${last})-{I}F{r})*B{r}"
    m[f"H{r}"] = f"=SUM(E{r}:G{r})"
    m[f"I{r}"] = (f'=IF(H{r}=0,"At/better than median",IF(E{r}=MAX(E{r}:G{r}),"Receivables",'
                  f'IF(F{r}=MAX(E{r}:G{r}),"Inventory","Payables")))')
s = last + 2
m[f"A{s}"], m[f"A{s}"].font = "Peer median", Font(bold=True)
m[f"C{s}"] = f"=MEDIAN(C{first}:C{last})"
m[f"A{s+1}"], m[f"A{s+1}"].font = "Total release, all companies", Font(bold=True)
m[f"H{s+1}"] = f"=SUM(H{first}:H{last})"
m[f"A{s+2}"], m[f"A{s+2}"].font = "Total release, excl. ITC", Font(bold=True)
m[f"H{s+2}"] = f'=H{s+1}-SUMIF(A{first}:A{last},"ITC",H{first}:H{last})'
m[f"A{s+3}"] = "ITC is excluded from the headline: its leaf-tobacco stock is aged for years by design."
for row in m.iter_rows(min_row=first, max_row=s + 2, min_col=2, max_col=8):
    for c in row:
        c.number_format = "#,##0;(#,##0)"
for col, w in zip("ABCDEFGHI", [28, 12, 10, 14, 13, 13, 13, 15, 20]):
    m.column_dimensions[col].width = w

# ---- Scenario: supply chain finance ----
sc = wb.create_sheet("SCF Scenario")
sc["A1"], sc["A1"].font = "Supply chain finance scenario", TITLE
sc["A2"] = "Bank pays suppliers early; buyer pays the bank later, extending its payable days."
sc["A3"], sc["B3"] = "Extra payable days (change me)", 15
sc["B3"].font = INPUT
sc["B3"].fill = PatternFill("solid", fgColor="FFF2CC")
header(sc, 4, ["Company", "Payable days now", "Payable days with SCF", "Cash released (Rs cr)"])
for k in range(n):
    r = first + k
    sc[f"A{r}"] = f"={I}A{r}"
    sc[f"B{r}"] = f"={I}F{r}"
    sc[f"C{r}"] = f"=B{r}+$B$3"
    sc[f"D{r}"] = f"=$B$3*Model!B{r}"
    sc[f"D{r}"].number_format = "#,##0"
sc[f"A{last+2}"], sc[f"A{last+2}"].font = "Total", Font(bold=True)
sc[f"D{last+2}"] = f"=SUM(D{first}:D{last})"
sc[f"D{last+2}"].number_format = "#,##0"
for col, w in zip("ABCD", [30, 16, 20, 20]):
    sc.column_dimensions[col].width = w

# ---- Trend ----
t = wb.create_sheet("CCC Trend")
t["A1"], t["A1"].font = "Cash conversion cycle (days), FY2015-FY2025", TITLE
years = [f"FY{y}" for y in range(2015, 2026)]
header(t, 3, ["Ticker"] + years + ["Change (days)"])
w = panel.pivot(index="ticker", columns="year", values="ccc")[years]
for k, (tick, row) in enumerate(w.iterrows()):
    r = 4 + k
    t.cell(row=r, column=1, value=tick)
    for j, v in enumerate(row, 2):
        t.cell(row=r, column=j, value=int(v)).font = INPUT
    t.cell(row=r, column=len(years) + 2, value=f"={get_column_letter(len(years)+1)}{r}-B{r}")
t.column_dimensions["A"].width = 14
img = Image(str(ROOT / "outputs" / "ccc_trend.png")); img.width, img.height = 720, 400
t.add_image(img, "A15")

ch = wb.create_sheet("Chart")
img2 = Image(str(ROOT / "outputs" / "cash_release.png")); img2.width, img2.height = 720, 400
ch.add_image(img2, "A1")

for sheet in wb.worksheets:
    sheet.freeze_panes = None
out = ROOT / "outputs" / "FMCG_Working_Capital_Model.xlsx"
wb.save(out)
print("saved", out)
