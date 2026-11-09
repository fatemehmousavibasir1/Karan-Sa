"""JSON-friendly data for the web frontend (dashboard, invoices, raw tables)."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from db import (
    INVOICES_VIEW_SQL,
    ITEMS_VIEW_SQL,
    STATUS_FA,
    TABLE_TITLES_FA,
    TABLES,
    get_conn,
    gregorian_to_jalali,
)

COLUMN_TITLES_FA = {
    "branch_id": "کد شعبه",
    "branch_name": "نام شعبه",
    "city": "شهر",
    "branch_type": "نوع شعبه",
    "address": "آدرس",
    "user_id": "کد کاربر",
    "full_name": "نام و نام خانوادگی",
    "role_title": "سمت",
    "access_level": "سطح دسترسی",
    "monthly_target_m_rial": "تارگت ماهانه (م.ر)",
    "phone": "تلفن",
    "product_id": "کد محصول",
    "sku_code": "کد کالا (SKU)",
    "product_name": "نام محصول",
    "brand": "برند",
    "category": "دسته",
    "origin_country": "کشور سازنده",
    "unit_cost_m_rial": "قیمت تمام‌شده (م.ر)",
    "unit_price_m_rial": "قیمت فروش (م.ر)",
    "stock_qty": "موجودی",
    "customer_id": "کد مشتری",
    "company_name": "نام شرکت",
    "industry_sector": "صنعت",
    "credit_limit_m_rial": "سقف اعتبار (م.ر)",
    "invoice_id": "شناسه فاکتور",
    "invoice_number": "شماره فاکتور",
    "invoice_date": "تاریخ صدور",
    "due_date": "سررسید",
    "sales_rep_id": "کد نماینده",
    "sales_rep": "نماینده فروش",
    "total_amount_m_rial": "مبلغ کل (م.ر)",
    "discount_m_rial": "تخفیف (م.ر)",
    "net_amount_m_rial": "مبلغ خالص (م.ر)",
    "payment_status": "وضعیت پرداخت",
    "payment_method": "روش پرداخت",
    "item_id": "ردیف",
    "quantity": "تعداد",
    "line_total_m_rial": "جمع ردیف (م.ر)",
    "total_sales": "مجموع فروش (م.ر)",
    "total_net_amount": "مجموع خالص (م.ر)",
    "total_net": "مجموع خالص (م.ر)",
    "total_quantity": "تعداد کل",
    "total_qty": "تعداد کل",
    "invoice_count": "تعداد فاکتور",
    "invoice_numbers": "شماره فاکتورها",
    "achieved_percentage": "درصد تحقق",
    "achieved_percent": "درصد تحقق",
    "remaining_credit": "اعتبار باقی‌مانده (م.ر)",
    "total_overdue": "جمع معوق (م.ر)",
    "total_paid": "جمع تسویه‌شده (م.ر)",
    "total_overdue_debt": "بدهی معوق (م.ر)",
    "difference": "تفاضل (م.ر)",
    "penetration": "ضریب نفوذ (٪)",
    "penetration_percentage": "ضریب نفوذ (٪)",
    "gross_profit_per_unit": "سود ناخالص هر واحد (م.ر)",
    "total_inventory_value": "ارزش موجودی (م.ر)",
    "total_discount": "جمع تخفیف (م.ر)",
    "access_decision": "نتیجه دسترسی",
    "user_branch": "شعبه کاربر",
    "invoice_branch": "شعبه فاکتور",
}

DATE_COLUMNS = {"invoice_date", "due_date"}


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _with_jalali(df: pd.DataFrame) -> pd.DataFrame:
    for col in DATE_COLUMNS & set(df.columns):
        df[col + "_fa"] = df[col].map(gregorian_to_jalali)
    return df


def dashboard() -> dict[str, Any]:
    with get_conn(read_only=True) as conn:
        def one(sql: str) -> tuple:
            return conn.execute(sql).fetchone()

        total_net, invoice_count, total_discount = one(
            "SELECT COALESCE(SUM(net_amount_m_rial),0), COUNT(*), COALESCE(SUM(discount_m_rial),0) FROM invoices"
        )
        by_status = {
            s: {"amount": a or 0, "count": c}
            for s, a, c in conn.execute(
                "SELECT payment_status, SUM(net_amount_m_rial), COUNT(*) FROM invoices GROUP BY payment_status"
            )
        }
        customers_count = one("SELECT COUNT(*) FROM customers")[0]
        products_count = one("SELECT COUNT(*) FROM products")[0]

    for code in STATUS_FA:
        by_status.setdefault(code, {"amount": 0, "count": 0})

    by_branch = _query(
        """SELECT b.branch_name AS label, b.branch_type AS type,
                  COALESCE(SUM(i.net_amount_m_rial),0) AS value, COUNT(i.invoice_id) AS count
           FROM branches b LEFT JOIN invoices i ON i.branch_id = b.branch_id
           GROUP BY b.branch_id ORDER BY value DESC"""
    )
    by_brand = _query(
        """SELECT p.brand AS label, SUM(it.line_total_m_rial) AS value, SUM(it.quantity) AS qty
           FROM invoice_items it JOIN products p ON p.product_id = it.product_id
           GROUP BY p.brand ORDER BY value DESC"""
    )
    top_customers = _query(
        """SELECT c.company_name AS label, c.industry_sector AS sector,
                  SUM(i.net_amount_m_rial) AS value, COUNT(*) AS count
           FROM invoices i JOIN customers c ON c.customer_id = i.customer_id
           GROUP BY c.customer_id ORDER BY value DESC LIMIT 6"""
    )
    top_reps = _query(
        """SELECT u.full_name AS label, b.branch_name AS branch, u.monthly_target_m_rial AS target,
                  COALESCE(SUM(i.net_amount_m_rial),0) AS value
           FROM users u
           JOIN invoices i ON i.sales_rep_id = u.user_id
           LEFT JOIN branches b ON b.branch_id = u.branch_id
           GROUP BY u.user_id ORDER BY value DESC"""
    )
    recent = _with_jalali(_query(INVOICES_VIEW_SQL.replace("ORDER BY i.invoice_id", "ORDER BY i.invoice_date DESC, i.invoice_id DESC LIMIT 6")))

    return {
        "kpi": {
            "total_net": total_net,
            "invoice_count": invoice_count,
            "total_discount": total_discount,
            "customers": customers_count,
            "products": products_count,
            "paid": by_status["PAID"],
            "cheque_pending": by_status["CHEQUE_PENDING"],
            "overdue": by_status["OVERDUE"],
        },
        "status_labels": STATUS_FA,
        "by_branch": _records(by_branch),
        "by_brand": _records(by_brand),
        "top_customers": _records(top_customers),
        "top_reps": _records(top_reps),
        "recent_invoices": _records(recent),
    }


def invoices() -> dict[str, Any]:
    inv = _with_jalali(_query(INVOICES_VIEW_SQL))
    items = _query(ITEMS_VIEW_SQL)
    counts = items.groupby("invoice_id").size().to_dict()
    inv["item_count"] = inv["invoice_id"].map(lambda i: int(counts.get(i, 0)))
    return {"invoices": _records(inv), "status_labels": STATUS_FA}


def invoice_detail(invoice_id: int) -> dict[str, Any] | None:
    inv = _with_jalali(_query(INVOICES_VIEW_SQL.replace("ORDER BY i.invoice_id", "WHERE i.invoice_id = ?"), (invoice_id,)))
    if inv.empty:
        return None
    items = _query(ITEMS_VIEW_SQL.replace("ORDER BY it.invoice_id, it.item_id", "WHERE it.invoice_id = ? ORDER BY it.item_id"), (invoice_id,))
    return {"invoice": _records(inv)[0], "items": _records(items)}


def tables_meta() -> list[dict[str, Any]]:
    with get_conn(read_only=True) as conn:
        return [
            {"name": t, "title": TABLE_TITLES_FA.get(t, t),
             "rows": conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]}
            for t in TABLES
        ]


def table_data(name: str) -> dict[str, Any]:
    if name not in TABLES:
        raise ValueError(name)
    df = _query(f"SELECT * FROM {name}")
    if "payment_status" in df.columns:
        df["payment_status"] = df["payment_status"].map(lambda s: STATUS_FA.get(s, s))
    for col in DATE_COLUMNS & set(df.columns):
        df[col] = df[col].map(gregorian_to_jalali)
    return {
        "name": name,
        "title": TABLE_TITLES_FA.get(name, name),
        "columns": [{"key": c, "title": COLUMN_TITLES_FA.get(c, c)} for c in df.columns],
        "rows": _records(df),
    }
