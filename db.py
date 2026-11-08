"""SQLite storage for KRS invoices (built from Dataset.txt)."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Iterator

import pandas as pd

from config import DATASET_FILE, DB_PATH, INVOICES_EXCEL

TABLES = ("branches", "users", "products", "customers", "invoices", "invoice_items")

STATUS_FA = {
    "PAID": "تسویه‌شده",
    "CHEQUE_PENDING": "چک در جریان",
    "OVERDUE": "معوق",
}


def gregorian_to_jalali(value: object) -> str:
    """'2026-09-25' -> '1405/07/03'."""
    if value is None:
        return ""
    m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})", str(value))
    if not m:
        return str(value)
    gy, gm, gd = (int(x) for x in m.groups())
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def _register_functions(conn: sqlite3.Connection) -> None:
    conn.create_function("jalali", 1, gregorian_to_jalali, deterministic=True)


def connect(*, read_only: bool = False) -> sqlite3.Connection:
    if not DB_PATH.exists():
        build_from_dataset()
    conn = sqlite3.connect(DB_PATH)
    _register_functions(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    if read_only:
        conn.execute("PRAGMA query_only = ON")
    return conn


@contextmanager
def get_conn(*, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    conn = connect(read_only=read_only)
    try:
        yield conn
        if not read_only:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_from_dataset(*, force: bool = False) -> None:
    """Create krs.db from the CREATE/INSERT script in Dataset.txt."""
    if DB_PATH.exists():
        if not force:
            return
        DB_PATH.unlink()
    script = DATASET_FILE.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def split_statements(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    for ch in sql:
        if ch == "'":
            in_single = not in_single
        if ch == ";" and not in_single:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    out = []
    for stmt in parts:
        lines = [ln for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        cleaned = "\n".join(lines).strip()
        if cleaned:
            out.append(cleaned)
    return out


def run_select(sql: str) -> pd.DataFrame:
    stmts = split_statements(sql)
    if len(stmts) != 1 or not re.match(r"^\s*(SELECT|WITH)\b", stmts[0], re.IGNORECASE):
        raise ValueError("فقط یک دستور SELECT مجاز است.")
    with get_conn(read_only=True) as conn:
        return pd.read_sql_query(stmts[0], conn)


_WRITE_OPS = {
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_TRANSACTION,
}


def _write_authorizer(action, arg1, arg2, dbname, source):  # noqa: ANN001
    if action not in _WRITE_OPS:
        return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        if arg1 not in TABLES:
            return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def recompute_invoice_totals(conn: sqlite3.Connection) -> None:
    """Keep header totals consistent with invoice_items."""
    conn.execute(
        """
        UPDATE invoices
        SET total_amount_m_rial = (
            SELECT ROUND(SUM(line_total_m_rial), 2)
            FROM invoice_items it WHERE it.invoice_id = invoices.invoice_id
        )
        WHERE EXISTS (
            SELECT 1 FROM invoice_items it WHERE it.invoice_id = invoices.invoice_id
        )
        """
    )
    conn.execute(
        "UPDATE invoices SET net_amount_m_rial = "
        "ROUND(total_amount_m_rial - COALESCE(discount_m_rial, 0), 2)"
    )


def run_write(sql: str) -> list[tuple[str, int]]:
    """Run INSERT/UPDATE/DELETE statements in one transaction."""
    stmts = split_statements(sql)
    if not stmts:
        raise ValueError("SQL خالی است.")
    for s in stmts:
        if not re.match(r"^\s*(INSERT|UPDATE|DELETE)\b", s, re.IGNORECASE):
            raise ValueError(f"فقط INSERT / UPDATE / DELETE مجاز است: {s[:80]}")
    results: list[tuple[str, int]] = []
    with get_conn() as conn:
        conn.set_authorizer(_write_authorizer)
        for s in stmts:
            cur = conn.execute(s)
            results.append((s, cur.rowcount))
        conn.set_authorizer(None)
        recompute_invoice_totals(conn)
    export_invoices_excel()
    return results


INVOICES_VIEW_SQL = """
SELECT i.invoice_id, i.invoice_number, i.invoice_date, i.due_date,
       c.company_name, b.branch_name, u.full_name AS sales_rep,
       i.total_amount_m_rial, i.discount_m_rial, i.net_amount_m_rial,
       i.payment_status, i.payment_method
FROM invoices i
LEFT JOIN customers c ON c.customer_id = i.customer_id
LEFT JOIN branches b ON b.branch_id = i.branch_id
LEFT JOIN users u ON u.user_id = i.sales_rep_id
ORDER BY i.invoice_id
"""

ITEMS_VIEW_SQL = """
SELECT it.item_id, i.invoice_number, it.invoice_id, p.sku_code, p.product_name, p.brand,
       it.quantity, it.unit_price_m_rial, it.line_total_m_rial
FROM invoice_items it
JOIN invoices i ON i.invoice_id = it.invoice_id
LEFT JOIN products p ON p.product_id = it.product_id
ORDER BY it.invoice_id, it.item_id
"""

INVOICE_COLS_FA = {
    "invoice_id": "شناسه",
    "invoice_number": "شماره فاکتور",
    "invoice_date": "تاریخ",
    "due_date": "سررسید",
    "company_name": "مشتری",
    "branch_name": "شعبه",
    "sales_rep": "نماینده فروش",
    "total_amount_m_rial": "مبلغ کل (م.ر)",
    "discount_m_rial": "تخفیف (م.ر)",
    "net_amount_m_rial": "خالص (م.ر)",
    "payment_status": "وضعیت پرداخت",
    "payment_method": "روش پرداخت",
}

ITEM_COLS_FA = {
    "item_id": "ردیف",
    "invoice_number": "شماره فاکتور",
    "invoice_id": "شناسه فاکتور",
    "sku_code": "کد کالا",
    "product_name": "کالا",
    "brand": "برند",
    "quantity": "تعداد",
    "unit_price_m_rial": "فی (م.ر)",
    "line_total_m_rial": "جمع ردیف (م.ر)",
}


def invoices_frame(*, persian: bool = True) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        df = pd.read_sql_query(INVOICES_VIEW_SQL, conn)
    if persian:
        df["invoice_date"] = df["invoice_date"].map(gregorian_to_jalali)
        df["due_date"] = df["due_date"].map(gregorian_to_jalali)
        df["payment_status"] = df["payment_status"].map(lambda s: STATUS_FA.get(s, s))
        df = df.rename(columns=INVOICE_COLS_FA)
    return df


def items_frame(*, persian: bool = True) -> pd.DataFrame:
    with get_conn(read_only=True) as conn:
        df = pd.read_sql_query(ITEMS_VIEW_SQL, conn)
    return df.rename(columns=ITEM_COLS_FA) if persian else df


def catalog_text() -> str:
    """Compact dump of the small lookup tables, embedded in SQL prompts."""
    queries = {
        "branches(branch_id, branch_name, city, branch_type)":
            "SELECT branch_id, branch_name, city, branch_type FROM branches ORDER BY branch_id",
        "users(user_id, full_name, role_title, access_level, branch_id, monthly_target_m_rial)":
            "SELECT user_id, full_name, role_title, access_level, branch_id, monthly_target_m_rial "
            "FROM users ORDER BY user_id",
        "products(product_id, sku_code, product_name, brand, category)":
            "SELECT product_id, sku_code, product_name, brand, category FROM products ORDER BY product_id",
        "customers(customer_id, company_name, industry_sector, city)":
            "SELECT customer_id, company_name, industry_sector, city FROM customers ORDER BY customer_id",
    }
    parts = []
    with get_conn(read_only=True) as conn:
        for title, q in queries.items():
            rows = conn.execute(q).fetchall()
            parts.append(title + ":\n" + "\n".join(" | ".join("" if v is None else str(v) for v in r) for r in rows))
        methods = [r[0] for r in conn.execute("SELECT DISTINCT payment_method FROM invoices")]
    parts.append("invoices.payment_method values: " + " | ".join(methods))
    return "\n\n".join(parts)


TABLE_TITLES_FA = {
    "branches": "شعب",
    "users": "کاربران و نمایندگان فروش",
    "products": "محصولات",
    "customers": "مشتریان",
    "invoices": "فاکتورها (خام)",
    "invoice_items": "اقلام فاکتور (خام)",
}


def table_frame(name: str) -> pd.DataFrame:
    if name not in TABLES:
        raise ValueError(f"جدول نامعتبر: {name}")
    with get_conn(read_only=True) as conn:
        return pd.read_sql_query(f"SELECT * FROM {name}", conn)


def export_invoices_excel() -> None:
    try:
        with pd.ExcelWriter(INVOICES_EXCEL, engine="openpyxl") as xw:
            invoices_frame().to_excel(xw, sheet_name="فاکتورها", index=False)
            items_frame().to_excel(xw, sheet_name="اقلام فاکتور", index=False)
    except PermissionError:
        # File is open in Excel; DB stays the source of truth.
        pass


def invoice_documents() -> list[dict]:
    """One text document per invoice (header + items) for Qdrant."""
    inv = invoices_frame(persian=False)
    items = items_frame(persian=False)
    docs = []
    for _, r in inv.iterrows():
        rows = items[items["invoice_id"] == r["invoice_id"]]
        lines = [
            f"- {it.product_name} (برند {it.brand}، کد {it.sku_code}): "
            f"تعداد {it.quantity}، فی {it.unit_price_m_rial} میلیون ریال، "
            f"جمع {it.line_total_m_rial} میلیون ریال"
            for it in rows.itertuples()
        ]
        text = (
            f"فاکتور شماره {r['invoice_number']} (شناسه {r['invoice_id']})\n"
            f"تاریخ صدور: {gregorian_to_jalali(r['invoice_date'])} ({r['invoice_date']})، "
            f"سررسید: {gregorian_to_jalali(r['due_date'])} ({r['due_date']})\n"
            f"مشتری: {r['company_name']}\n"
            f"شعبه: {r['branch_name']}، نماینده فروش: {r['sales_rep']}\n"
            f"مبلغ کل: {r['total_amount_m_rial']} میلیون ریال، تخفیف: {r['discount_m_rial']}، "
            f"مبلغ خالص: {r['net_amount_m_rial']} میلیون ریال\n"
            f"وضعیت پرداخت: {STATUS_FA.get(r['payment_status'], r['payment_status'])}، "
            f"روش پرداخت: {r['payment_method']}\n"
            "اقلام:\n" + "\n".join(lines)
        )
        docs.append(
            {
                "invoice_id": int(r["invoice_id"]),
                "invoice_number": r["invoice_number"],
                "text": text,
            }
        )
    return docs


def df_to_markdown(df: pd.DataFrame, max_rows: int = 50) -> str:
    if df.empty:
        return "(نتیجه‌ای یافت نشد)"
    shown = df.head(max_rows)
    cols = [str(c) for c in shown.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in shown.itertuples(index=False):
        out.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    if len(df) > max_rows:
        out.append(f"\n… و {len(df) - max_rows} ردیف دیگر")
    return "\n".join(out)
