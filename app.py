from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import pandas as pd
try:
    import streamlit as st
except ModuleNotFoundError:  # Core accounting tests can run before UI dependencies are installed.
    st = None

TEAM_ID = "TEAM-1"
COURSE = "Precalculus"
PATHWAY_ID = "ART-2"
BUSINESS = "Design and animation studio"
STATE_VERSION = "v1"
CURRENCY = "USD"
D = Decimal
ZERO = D("0")
CENT = D("0.01")

STARTUP = {
    "owner_contribution": D("7000"),
    "equipment_assets": D("1800"),
    "preopening_expense": D("1200"),
    "opening_inventory": D("0"),
    "opening_cash": D("4000"),
    "beginning_retained_earnings": D("-1200"),
}
DEFAULT_VARIABLE = {
    "creative_labor": D("25"),
    "licensed_assets": D("10"),
    "rendering": D("5"),
    "delivery_print": D("5"),
}
DEFAULT_FIXED = {
    "software": D("250"),
    "workspace": D("250"),
    "admin": D("150"),
    "equipment_maintenance": D("150"),
}
OFFERINGS = [
    ("branding", "Branding package"),
    ("animation", "Animated explainer"),
    ("poster", "Event poster package"),
]
REQUIRED_SNAPSHOT_FIELDS = {
    "team_id", "course", "pathway_id", "business", "state_version",
    "opening_cash_cents", "cash_cents", "parameters", "ledger", "run_ids",
}

def dec(value: Any) -> Decimal:
    """Convert user-entered values safely through their string representation."""
    return D(str(value))

def cents(value: Any) -> int:
    return int((dec(value) * 100).quantize(D("1"), rounding=ROUND_HALF_UP))

def from_cents(value: int) -> Decimal:
    return D(int(value)) / D("100")

def money(value: Any) -> str:
    amount = dec(value).quantize(CENT, rounding=ROUND_HALF_UP)
    return f"${amount:,.2f}"

def default_parameters() -> dict:
    return {
        "base_price": "180",
        "D0": 18,
        "staff_hours": "90",
        "hours_per_unit": "6",
        "revision_hours_per_project": "0",
        "extra_revision_hourly_cost": "5",
        "asset_license_verified": True,
        "variable_lines": {k: str(v) for k, v in DEFAULT_VARIABLE.items()},
        "fixed_lines": {k: str(v) for k, v in DEFAULT_FIXED.items()},
        "advertising": "0",
        "snapshot_id": "",
        "simulation_date": date.today().isoformat(),
        "random_seed": 0,
        "refund_amount": "0",
        "loan_principal": "0",
        "interest": "0",
        "additional_capex": "0",
        "new_owner_cash": "0",
        "loan_cash": "0",
        "selected_level": "Advanced",
    }

def validate_parameters(p: dict) -> None:
    required = ["base_price", "D0", "staff_hours", "hours_per_unit",
                "revision_hours_per_project", "extra_revision_hourly_cost",
                "variable_lines", "fixed_lines"]
    missing = [x for x in required if x not in p]
    if missing:
        raise ValueError(f"Missing parameter(s): {', '.join(missing)}")
    if dec(p["base_price"]) <= 0:
        raise ValueError("Base price must be greater than zero.")
    if int(p["D0"]) < 0 or float(p["D0"]) != int(p["D0"]):
        raise ValueError("D0 must be a nonnegative integer.")
    if dec(p["staff_hours"]) < 0 or dec(p["revision_hours_per_project"]) < 0:
        raise ValueError("Staff hours and revision hours must be nonnegative.")
    if dec(p["hours_per_unit"]) <= 0:
        raise ValueError("Hours per unit must be greater than zero.")
    if dec(p["extra_revision_hourly_cost"]) < 0:
        raise ValueError("Extra revision hourly cost must be nonnegative.")
    for group in ("variable_lines", "fixed_lines"):
        for name, value in p[group].items():
            if dec(value) < 0:
                raise ValueError(f"{group}.{name} cannot be negative.")
    for key in ("advertising", "refund_amount", "loan_principal", "interest",
                "additional_capex", "new_owner_cash", "loan_cash"):
        if dec(p.get(key, "0")) < 0:
            raise ValueError(f"{key} cannot be negative.")

def capacity(p: dict) -> int:
    validate_parameters(p)
    hours = dec(p["hours_per_unit"]) + dec(p["revision_hours_per_project"])
    return int((dec(p["staff_hours"]) / hours).to_integral_value(rounding="ROUND_FLOOR"))

def variable_per_unit(p: dict) -> Decimal:
    validate_parameters(p)
    lines = sum((dec(v) for v in p["variable_lines"].values()), ZERO)
    return lines + dec(p["revision_hours_per_project"]) * dec(p["extra_revision_hourly_cost"])

def calculate_month(p: dict, requested: int, *, capacity_override: int | None = None,
                    ad_cost: Any | None = None) -> dict:
    validate_parameters(p)
    if int(requested) < 0:
        raise ValueError("Requested projects cannot be negative.")
    cap = capacity(p) if capacity_override is None else int(capacity_override)
    if cap < 0:
        raise ValueError("Capacity cannot be negative.")
    sold = min(int(requested), cap)
    price = dec(p["base_price"])
    unit_cost = variable_per_unit(p)
    revenue = price * sold
    variable_expense = unit_cost * sold
    fixed_expense = sum((dec(v) for v in p["fixed_lines"].values()), ZERO)
    marketing = dec(p["advertising"] if ad_cost is None else ad_cost)
    interest = dec(p.get("interest", "0"))
    principal = dec(p.get("loan_principal", "0"))
    capex = dec(p.get("additional_capex", "0"))
    owner_cash = dec(p.get("new_owner_cash", "0"))
    loan_cash = dec(p.get("loan_cash", "0"))
    refund = dec(p.get("refund_amount", "0"))
    total_expense = variable_expense + fixed_expense + marketing + interest
    operating_profit = revenue - variable_expense - fixed_expense - marketing - interest
    return {
        "requested": int(requested), "capacity": cap, "sold": sold,
        "price": price, "unit_variable_cost": unit_cost,
        "revenue": revenue, "variable_expense": variable_expense,
        "fixed_expense": fixed_expense, "marketing": marketing,
        "interest": interest, "principal": principal, "capex": capex,
        "owner_cash": owner_cash, "loan_cash": loan_cash, "refund": refund,
        "total_expense": total_expense, "profit": operating_profit,
    }

def seasonal_demand(D0: Any, month_index: int) -> float:
    return float(D0) * (1 + 0.20 * math.sin(2 * math.pi * (int(month_index) - 1) / 12))

def average_cost(sold: int, fixed: Any = D("800"), variable: Any = D("45")) -> Decimal | None:
    if int(sold) == 0:
        return None
    return dec(fixed) / D(int(sold)) + dec(variable)

def initial_state() -> dict:
    return {
        "team_id": TEAM_ID, "course": COURSE, "pathway_id": PATHWAY_ID,
        "business": BUSINESS, "state_version": STATE_VERSION,
        "opening_cash_cents": cents(STARTUP["opening_cash"]),
        "cash_cents": cents(STARTUP["opening_cash"]),
        "debt_cents": 0,
        "parameters": default_parameters(),
        "ledger": [], "run_ids": [],
    }

def _ledger_row(transaction_id: str, tx_date: str, event_type: str,
                category: str, amount: Decimal, quantity: int = 0,
                unit_price: Decimal = ZERO, offering_id: str = "",
                campaign_id: str = "", financing_type: str = "") -> dict:
    if amount < 0:
        raise ValueError("Ledger amounts must be nonnegative; event_type determines direction.")
    return {
        "transaction_id": transaction_id, "date": tx_date,
        "event_type": event_type, "category": category,
        "amount": cents(amount), "quantity": int(quantity),
        "unit_price": cents(unit_price), "offering_id": offering_id,
        "campaign_id": campaign_id, "financing_type": financing_type,
        "state_version": STATE_VERSION,
    }

def run_month(state: dict, *, run_id: str, tx_date: str, requested: int,
              offering_id: str = "branding", capacity_override: int | None = None,
              ad_cost: Any | None = None) -> dict:
    if not run_id or run_id in state["run_ids"]:
        raise ValueError(f"Duplicate or empty run_id rejected: {run_id!r}")
    # ISO date validation prevents ambiguous ledger dates.
    date.fromisoformat(tx_date)
    p = state["parameters"]
    result = calculate_month(p, requested, capacity_override=capacity_override, ad_cost=ad_cost)
    rows = []
    tid = lambda suffix: f"{run_id}-{suffix}"
    if result["revenue"]:
        rows.append(_ledger_row(tid("revenue"), tx_date, "revenue", "project_sales",
                                result["revenue"], result["sold"], result["price"], offering_id))
    for key, category in [("variable_expense", "delivery_cost"),
                          ("fixed_expense", "monthly_fixed_cost"),
                          ("marketing", "advertising"),
                          ("interest", "interest_expense"),
                          ("principal", "loan_principal"),
                          ("capex", "capital_expenditure"),
                          ("owner_cash", "owner_contribution"),
                          ("loan_cash", "loan_proceeds"),
                          ("refund", "refunds")]:
        amount = result[key]
        if amount:
            event = "cash_in" if key in ("owner_cash", "loan_cash", "refund") else "cash_out"
            financing = "loan" if key in ("loan_cash", "principal", "interest") else (
                "owner" if key == "owner_cash" else "")
            rows.append(_ledger_row(tid(key), tx_date, event, category, amount,
                                    financing_type=financing))
    # Cash uses cash costs, financing and capital movements; revenue is cash received.
    cash_delta = (result["revenue"] - result["variable_expense"] -
                  result["fixed_expense"] - result["marketing"] -
                  result["interest"] - result["principal"] - result["capex"] +
                  result["owner_cash"] + result["loan_cash"] + result["refund"])
    state["cash_cents"] += cents(cash_delta)
    state["debt_cents"] += cents(result["loan_cash"] - result["principal"])
    state["ledger"].extend(rows)
    state["run_ids"].append(run_id)
    result["closing_cash"] = from_cents(state["cash_cents"])
    result["transaction_count"] = len(rows)
    return result

def snapshot_dict(state: dict) -> dict:
    return {
        "team_id": state["team_id"], "course": state["course"],
        "pathway_id": state["pathway_id"], "business": state["business"],
        "state_version": state["state_version"],
        "opening_cash_cents": int(state["opening_cash_cents"]),
        "cash_cents": int(state["cash_cents"]),
        "debt_cents": int(state["debt_cents"]),
        "parameters": state["parameters"], "ledger": state["ledger"],
        "run_ids": state["run_ids"],
    }

def reconcile_cash(snapshot: dict) -> int:
    cash = int(snapshot["opening_cash_cents"])
    for row in snapshot["ledger"]:
        amount = int(row["amount"])
        if row["event_type"] == "revenue" or row["event_type"] == "cash_in":
            cash += amount
        elif row["event_type"] == "cash_out":
            cash -= amount
        else:
            raise ValueError(f"Unsupported ledger event_type: {row['event_type']}")
    return cash

def validate_snapshot(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Snapshot must be a JSON object.")
    missing = REQUIRED_SNAPSHOT_FIELDS - set(data)
    if missing:
        raise ValueError(f"Snapshot missing required fields: {', '.join(sorted(missing))}")
    if data["team_id"] != TEAM_ID:
        raise ValueError(f"Wrong team_id: expected {TEAM_ID}, received {data['team_id']!r}.")
    if data["state_version"] != STATE_VERSION:
        raise ValueError(
            f"Stale or unsupported state_version {data['state_version']!r}; "
            f"this app requires {STATE_VERSION}. No data was loaded."
        )
    for key in ("opening_cash_cents", "cash_cents", "debt_cents"):
        if not isinstance(data[key], int) or data[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer number of cents.")
    validate_parameters(data["parameters"])
    if not isinstance(data["ledger"], list) or not isinstance(data["run_ids"], list):
        raise ValueError("Snapshot ledger and run_ids must be lists.")
    ids = set()
    for row in data["ledger"]:
        required = {"transaction_id", "date", "event_type", "category", "amount",
                    "quantity", "unit_price", "offering_id", "campaign_id",
                    "financing_type", "state_version"}
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError("A ledger transaction is missing required fields.")
        date.fromisoformat(row["date"])
        if row["state_version"] != STATE_VERSION:
            raise ValueError("Ledger contains a stale state_version.")
        for k in ("amount", "quantity", "unit_price"):
            if not isinstance(row[k], int) or row[k] < 0:
                raise ValueError(f"Ledger {k} must be a nonnegative integer.")
        if row["transaction_id"] in ids:
            raise ValueError("Duplicate transaction_id found in snapshot.")
        ids.add(row["transaction_id"])
    if len(set(data["run_ids"])) != len(data["run_ids"]):
        raise ValueError("Snapshot contains duplicate run_ids.")
    if reconcile_cash(data) != data["cash_cents"]:
        raise ValueError("Snapshot cash reconciliation failed: ledger total does not equal cash_cents.")
    return data

def restore_snapshot(data: Any) -> dict:
    snap = validate_snapshot(data)
    return {
        "team_id": snap["team_id"], "course": snap["course"],
        "pathway_id": snap["pathway_id"], "business": snap["business"],
        "state_version": snap["state_version"],
        "opening_cash_cents": snap["opening_cash_cents"],
        "cash_cents": snap["cash_cents"], "debt_cents": snap["debt_cents"],
        "parameters": snap["parameters"], "ledger": snap["ledger"],
        "run_ids": snap["run_ids"],
    }

def ledger_frame(ledger: list[dict]) -> pd.DataFrame:
    cols = ["transaction_id", "date", "event_type", "category", "amount",
            "quantity", "unit_price", "offering_id", "campaign_id",
            "financing_type", "state_version"]
    df = pd.DataFrame(ledger, columns=cols)
    if not df.empty:
        df["amount_usd"] = df["amount"].map(lambda x: float(from_cents(x)))
        df["unit_price_usd"] = df["unit_price"].map(lambda x: float(from_cents(x)))
        df["date"] = pd.to_datetime(df["date"])
    return df

def aggregate_ledger(ledger: list[dict], frequency: str) -> pd.DataFrame:
    """Aggregate actual ledger amounts. Daily monthly allocations are not synthesized."""
    df = ledger_frame(ledger)
    if df.empty:
        return pd.DataFrame(columns=["period", "event_type", "category", "amount_usd"])
    if frequency == "Daily":
        df["period"] = df["date"].dt.strftime("%Y-%m-%d")
    elif frequency == "Monthly":
        df["period"] = df["date"].dt.to_period("M").astype(str)
    else:
        df["period"] = df["date"].dt.year.astype(str)
    return (df.groupby(["period", "event_type", "category"], as_index=False)
              ["amount_usd"].sum())

def fixture_replay() -> tuple[dict, pd.DataFrame]:
    fixture_path = Path(__file__).parent / "sample_data" / "monthly_fixture.csv"
    fixture = pd.read_csv(fixture_path, dtype={"month": str})
    state = initial_state()
    outputs = []
    for row in fixture.to_dict("records"):
        month = str(row["month"])
        tx_date = f"{month}-01"
        result = run_month(state, run_id=f"fixture-{month}", tx_date=tx_date,
                           requested=int(row["requested"]),
                           capacity_override=int(row["capacity_override"]),
                           ad_cost=dec(row["ad_cost"]))
        outputs.append({
            "Month": month, "Sold": result["sold"], "Revenue": result["revenue"],
            "Total Expense": result["total_expense"], "Profit": result["profit"],
            "Closing Cash": result["closing_cash"],
        })
    return state, pd.DataFrame(outputs)

def _init_session():
    if "cvl_state" not in st.session_state:
        st.session_state.cvl_state = initial_state()
    if "forecast_multiplier" not in st.session_state:
        st.session_state.forecast_multiplier = 1.0

def _money_input(label: str, value: str, key: str, min_value: float = 0.0):
    return st.number_input(label, min_value=min_value, value=float(dec(value)),
                           step=5.0, format="%.2f", key=key)

def _show_math_panel(p: dict, level: str):
    cap = capacity(p)
    fixed = sum((dec(v) for v in p["fixed_lines"].values()), ZERO)
    variable = variable_per_unit(p)
    D0 = int(p["D0"])
    p0 = dec(p["base_price"])
    st.subheader("Math Skills & Challenge Level")
    level = st.selectbox("Challenge level", ["Foundation", "Applied", "Advanced"],
                         index=["Foundation", "Applied", "Advanced"].index(level),
                         key="math_level")
    st.caption(f"Selected skill: {level} · Course: {COURSE} · Pathway: {PATHWAY_ID}")
    if level == "Foundation":
        st.markdown("**Average cost function**")
        st.latex(r"A(s)=\\frac{F}{s}+v,\\quad 0<s\\leq\\text{capacity}")
        st.write(f"F = {money(fixed)} per month; v = {money(variable)} per project; s = delivered projects.")
        st.write(f"Domain: 0 < s ≤ {cap}. A(0) is undefined; vertical asymptote s=0; horizontal asymptote y={money(variable)}.")
        st.warning("Practical-domain warning: the curve is defined only for positive delivered projects and the displayed operational capacity.")
        xs = list(range(1, max(cap, 1) + 1))
        ys = [float(average_cost(x, fixed, variable)) for x in xs]
        st.line_chart(pd.DataFrame({"Projects delivered": xs, "Average cost (USD/project)": ys}).set_index("Projects delivered"))
        st.dataframe(pd.DataFrame({"s (projects)": [0] + xs,
                                   "A(s) (USD/project)": ["Undefined"] + [money(average_cost(x, fixed, variable)) for x in xs]}),
                     use_container_width=True)
        st.caption("Interpretation: explain why average cost rises sharply as output approaches zero.")
    elif level == "Applied":
        st.markdown("**Composed price, demand, sales, revenue, cost, and profit functions**")
        st.latex(r"q(p)=\\max(0,2D_0-(D_0/p_0)p)")
        st.latex(r"s(p)=\\min(\\text{capacity},q(p)),\\ R(p)=p\\,s(p)")
        st.latex(r"C(s(p))=F+v\\,s(p),\\ P(p)=R(p)-C(s(p))")
        st.write(f"Inputs: p in USD/project, 0 ≤ p ≤ {money(2*p0)}; output q and s in projects/month; F={money(fixed)}, v={money(variable)}.")
        breakpoint = p0 * (D("2") - D(cap) / D(D0)) if D0 > 0 else None
        if breakpoint is not None and D("0") <= breakpoint <= D("2") * p0:
            st.info(f"Capacity breakpoint: p = p₀(2 − capacity/D₀) = {money(breakpoint)}.")
        else:
            st.info("No capacity breakpoint lies in the specified price domain.")
        prices = [D(i) for i in range(0, int(2*p0) + 1, 5)]
        rows = []
        for price in prices:
            q = max(0.0, 2*D0 - (D0/float(p0))*float(price))
            s = min(cap, q)
            revenue = float(price) * s
            cost = float(fixed) + float(variable) * s
            rows.append({"Price": float(price), "Demand q(p)": q, "Continuous sales s(p)": s,
                         "Revenue": revenue, "Cost": cost, "Profit": revenue-cost})
        frame = pd.DataFrame(rows).set_index("Price")
        st.line_chart(frame[["Demand q(p)", "Continuous sales s(p)"]])
        st.line_chart(frame[["Revenue", "Cost", "Profit"]])
        st.dataframe(frame.head(12), use_container_width=True)
        st.caption("Input-output mapping: price → continuous demand → capacity-limited continuous sales → revenue/cost/profit. Real transactions are integer projects; curves are continuous and must not be mistaken for rounded ledger transactions.")
        st.write("Assumptions: linear price response, constant unit cost, fixed monthly cost, no backlog, and no demand beyond the stated price domain.")
    else:
        st.markdown("**Seasonal trigonometric demand model**")
        st.latex(r"D(t)=D_0\\left(1+0.20\\sin\\left(\\frac{2\\pi(t-1)}{12}\\right)\\right)")
        st.write(f"t = month index (months); D₀ = {D0} requested projects/month; period = 12 months.")
        st.write(f"Peak at t=4: {seasonal_demand(D0,4):.1f} projects (1.2 × D₀). Minimum at t=10: {seasonal_demand(D0,10):.1f} projects (0.8 × D₀).")
        months = list(range(1, 25))
        demand = [seasonal_demand(D0, t) for t in months]
        realized = [min(cap, x) for x in demand]
        st.line_chart(pd.DataFrame({"Original seasonal demand": demand,
                                    "Capacity-limited realized sales": realized},
                                   index=months))
        st.dataframe(pd.DataFrame({"Month index t": months[:12],
                                   "Demand (projects)": [round(x, 2) for x in demand[:12]],
                                   "Realized sales (projects)": [round(x, 2) for x in realized[:12]]}),
                     use_container_width=True)
        st.write(f"Capacity = {cap} projects/month; realized sales are clipped at capacity. Assumptions: fixed 20% sinusoidal seasonality, stable baseline demand and capacity, and month-index periodicity.")
        st.warning("Extrapolation limit: this is a repeating illustrative model, not a forecast of market shocks, changing prices, or long-term business growth.")
        st.caption("Interpretation: compare the seasonal demand peaks with the flat capacity ceiling and identify months with unmet demand.")

def main():
    if st is None:
        raise RuntimeError("Streamlit is required to launch the interface. Install requirements.txt first.")
    st.set_page_config(page_title="Career Venture Lab · Stage 1", page_icon="🎨", layout="wide")
    _init_session()
    state = st.session_state.cvl_state
    p = state["parameters"]
    st.title("Career Venture Lab")
    st.caption("Stage 1 · Offline-first business simulation · TEAM-1 · Precalculus · ART-2")
    st.markdown("**Design and animation studio** · Branding package · Animated explainer · Event poster package")
    with st.expander("Startup financing & opening balances", expanded=False):
        st.write({
            "Owner contribution": money(7000), "Equipment assets (capital asset)": money(1800),
            "Pre-opening expense (already expensed)": money(1200), "Opening inventory": money(0),
            "Post-startup spendable cash": money(4000),
            "Beginning retained earnings": money(-1200),
        })
        st.caption("Opening assets = owner equity − pre-opening expense. Equipment and inventory are not expensed again.")
    tabs = st.tabs(["Business Simulator", "Math Skills", "Ledger & Forecasts", "Snapshots & Export", "Fixture Test Mode", "Stage 2/3"])
    with tabs[0]:
        left, right = st.columns(2)
        with left:
            st.subheader("Editable operating assumptions")
            p["base_price"] = str(_money_input("Base price per project (USD)", p["base_price"], "base_price"))
            p["D0"] = int(st.number_input("Requested projects/month (D₀)", min_value=0, step=1, value=int(p["D0"])))
            p["staff_hours"] = str(st.number_input("Productive staff hours/month", min_value=0.0, value=float(dec(p["staff_hours"])), step=5.0))
            p["hours_per_unit"] = str(st.number_input("Productive hours/project", min_value=0.01, value=float(dec(p["hours_per_unit"])), step=0.5))
            p["revision_hours_per_project"] = str(st.number_input("Revision hours/project", min_value=0.0, value=float(dec(p["revision_hours_per_project"])), step=0.5))
            p["extra_revision_hourly_cost"] = str(_money_input("Extra revision hourly cost", p["extra_revision_hourly_cost"], "revision_cost"))
            p["asset_license_verified"] = st.checkbox("Asset license verified (publishing gate)", value=bool(p["asset_license_verified"]))
            st.subheader("Variable costs per delivered project")
            for key, val in list(p["variable_lines"].items()):
                p["variable_lines"][key] = str(_money_input(key.replace("_", " ").title(), val, f"var_{key}"))
            st.subheader("Monthly fixed costs")
            for key, val in list(p["fixed_lines"].items()):
                p["fixed_lines"][key] = str(_money_input(key.replace("_", " ").title(), val, f"fixed_{key}"))
        with right:
            st.subheader("Monthly run")
            st.write(f"Calculated normal capacity: **{capacity(p)} projects/month**")
            st.write(f"Variable cost/project: **{money(variable_per_unit(p))}**")
            requested = int(st.number_input("Requested projects for this run", min_value=0, value=int(p["D0"]), step=1))
            run_date = st.date_input("Transaction date", value=date.today())
            offering = st.selectbox("Offering", options=[x[0] for x in OFFERINGS],
                                    format_func=lambda x: dict(OFFERINGS)[x])
            p["advertising"] = str(_money_input("Advertising campaign expense (USD)", p.get("advertising", "0"), "ad_spend"))
            st.subheader("Optional financing & controls")
            p["loan_principal"] = str(_money_input("Loan principal repayment", p.get("loan_principal", "0"), "loan_principal"))
            p["interest"] = str(_money_input("Interest expense", p.get("interest", "0"), "interest"))
            p["additional_capex"] = str(_money_input("Additional capital expenditure", p.get("additional_capex", "0"), "capex"))
            p["new_owner_cash"] = str(_money_input("New owner cash contribution", p.get("new_owner_cash", "0"), "owner_cash"))
            p["loan_cash"] = str(_money_input("New loan proceeds", p.get("loan_cash", "0"), "loan_cash"))
            p["refund_amount"] = str(_money_input("Refunds received", p.get("refund_amount", "0"), "refund"))
            st.caption("Financing and capital movements affect cash, not operating revenue. Principal reduces cash/debt; interest is an expense; capex is a cash outflow.")
            if st.button("Run monthly simulation", type="primary"):
                try:
                    validate_parameters(p)
                    if not p["asset_license_verified"]:
                        st.warning("Publishing is blocked until asset licensing is verified. Internal calculations remain available.")
                    run_id = str(uuid.uuid4())
                    result = run_month(state, run_id=run_id, tx_date=run_date.isoformat(),
                                       requested=requested, offering_id=offering)
                    st.success(f"Run saved. Run ID: {run_id}")
                    st.metric("Closing cash", money(result["closing_cash"]))
                    st.write({k: money(result[k]) for k in ("revenue", "variable_expense", "fixed_expense", "marketing", "total_expense", "profit")})
                except Exception as exc:
                    st.error(str(exc))
        st.metric("Current cash balance", money(from_cents(state["cash_cents"])))
    with tabs[1]:
        _show_math_panel(p, p.get("selected_level", "Advanced"))
        p["selected_level"] = st.session_state.get("math_level", "Advanced")
    with tabs[2]:
        st.subheader("Actual ledger")
        if state["ledger"]:
            df = ledger_frame(state["ledger"])
            st.dataframe(df, use_container_width=True)
            freq = st.selectbox("Aggregation view", ["Daily", "Monthly", "Yearly"])
            if freq == "Daily":
                st.info("Modeled daily view: monthly-run entries appear on their recorded transaction dates. Each monthly amount is counted once; it is not multiplied by 30 or spread into fabricated transactions.")
            st.dataframe(aggregate_ledger(state["ledger"], freq), use_container_width=True)
        else:
            st.info("No actual transactions yet. Run a simulation or use Fixture Test Mode.")
        st.subheader("Separate forecast scenarios (not posted to actual ledger)")
        forecast_base = calculate_month(p, int(p["D0"]))
        forecast_rows = []
        for label, mult in [("Downside", 0.90), ("Baseline", 1.00), ("Upside", 1.10)]:
            forecast_demand = max(0, int(round(int(p["D0"]) * mult)))
            forecast = calculate_month(p, forecast_demand)
            forecast_rows.append({"Scenario": label, "Multiplier": mult,
                                  "Requested": forecast_demand, "Sold": forecast["sold"],
                                  "Revenue": money(forecast["revenue"]),
                                  "Profit": money(forecast["profit"])})
        st.dataframe(pd.DataFrame(forecast_rows), use_container_width=True)
        st.caption("Forecasts are hypothetical calculations and never create actual ledger transactions.")
    with tabs[3]:
        st.subheader("JSON snapshot")
        snap = snapshot_dict(state)
        st.download_button("Save Snapshot (JSON)", data=json.dumps(snap, indent=2),
                           file_name=f"career_venture_lab_{TEAM_ID}_{STATE_VERSION}.json",
                           mime="application/json")
        uploaded = st.file_uploader("Load/Restore Snapshot (JSON)", type=["json"])
        if uploaded is not None and st.button("Validate and restore snapshot"):
            try:
                restored = restore_snapshot(json.loads(uploaded.getvalue().decode("utf-8")))
                st.session_state.cvl_state = restored
                st.success("Snapshot validated and restored. Cash reconciles to the dated ledger.")
                st.rerun()
            except Exception as exc:
                st.error(f"Snapshot rejected: {exc}")
        csv_data = ledger_frame(state["ledger"]).to_csv(index=False)
        st.download_button("Export actual ledger (CSV)", data=csv_data,
                           file_name="career_venture_lab_ledger.csv", mime="text/csv")
        st.caption("Snapshots require matching team_id and state_version v1, nonnegative numeric inputs, unique transactions/runs, and exact cash reconciliation.")
    with tabs[4]:
        st.warning("FIXTURE TEST MODE — isolated test replay. This resets a separate temporary state to $4,000 opening cash and does not modify your normal simulator ledger.")
        if st.button("Replay exact 3-month fixture", type="primary"):
            fixture_state, results = fixture_replay()
            st.session_state.fixture_results = results
            st.session_state.fixture_state = fixture_state
        if "fixture_results" in st.session_state:
            results = st.session_state.fixture_results
            expected = [
                ("2027-01", 15, D("2700"), D("1475"), D("1225"), D("5225")),
                ("2027-02", 15, D("2700"), D("1575"), D("1125"), D("6350")),
                ("2027-03", 11, D("1980"), D("1295"), D("685"), D("7035")),
            ]
            st.dataframe(results.assign(**{c: results[c].map(money) for c in ["Revenue", "Total Expense", "Profit", "Closing Cash"]}),
                         use_container_width=True)
            passed = all(
                row["Month"] == exp[0] and int(row["Sold"]) == exp[1] and
                row["Revenue"] == exp[2] and row["Total Expense"] == exp[3] and
                row["Profit"] == exp[4] and row["Closing Cash"] == exp[5]
                for (_, row), exp in zip(results.iterrows(), expected)
            )
            if passed:
                st.success("All fixture results match the required expected values.")
            else:
                st.error("Fixture result mismatch. Review the operating cost assumptions.")
            st.caption("Fixture replay uses capacity_override from the fixture and a separate state; it is never mixed with normal runs.")
    with tabs[5]:
        st.subheader("Coming in Stage 2/3")
        for module in ["AI Department Tabs", "Full Report Center", "Costed Marketing Studio", "Assessment Panel"]:
            st.info(f"{module} — Coming in Stage 2/3")

if __name__ == "__main__":
    main()
