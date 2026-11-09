"use strict";

/* ================= Helpers ================= */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const faNum = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 });
const fmt = (v) => (v === null || v === undefined || v === "" ? "—" : isFinite(v) ? faNum.format(Number(v)) : String(v));
const faDigits = (s) => String(s ?? "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

let toastTimer;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

const PALETTE = ["#1F2839", "#B69D74", "#4A5874", "#8F7650", "#34415C", "#C9B48C", "#5E6B85", "#A08660"];
const initials = (name) => (name || "؟").trim().split(/\s+/).slice(-1)[0].slice(0, 1);

const STATE = {
  meta: { columns: {}, status_labels: { PAID: "تسویه‌شده", CHEQUE_PENDING: "چک در جریان", OVERDUE: "معوق" } },
  cache: {},
  invFilter: "ALL",
  currentTable: null,
  busy: false,
};

const statusPill = (code) => `<span class="pill pill-${esc(code)}">${esc(STATE.meta.status_labels[code] || code)}</span>`;
const colTitle = (key) => STATE.meta.columns[key] || String(key).replace(/_/g, " ");

/* ================= Router ================= */
const VIEWS = {
  dashboard: { title: "داشبورد", subtitle: "نمای کلی فروش و وضعیت مطالبات", load: loadDashboard },
  chat: { title: "گفتگو با دستیار", subtitle: "", load: () => $("#chat-input").focus() },
  invoices: { title: "فاکتورها", subtitle: "فهرست کامل فاکتورها؛ برای مشاهده اقلام روی هر ردیف کلیک کنید", load: loadInvoices },
  tables: { title: "همه جداول", subtitle: "داده‌های خام شش جدول پایگاه داده", load: loadTables },
};

function route() {
  const name = (location.hash || "#dashboard").slice(1);
  const view = VIEWS[name] ? name : "dashboard";
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  $$(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  $("#page-title").textContent = VIEWS[view].title;
  $("#page-subtitle").textContent = VIEWS[view].subtitle;
  $("#sidebar").classList.remove("open");
  VIEWS[view].load();
}

/* ================= Dashboard ================= */
const ICONS = {
  money: '<svg viewBox="0 0 24 24"><path d="M3 6h18v12H3zm9 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6M6 8a2 2 0 0 1-2 2v4a2 2 0 0 1 2 2h12a2 2 0 0 1 2-2v-4a2 2 0 0 1-2-2z"/></svg>',
  doc: '<svg viewBox="0 0 24 24"><path d="M6 2h9l5 5v15H4V2zm8 1.5V8h4.5zM7 12v1.6h10V12zm0 4v1.6h10V16z"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m-2 15-5-5 1.4-1.4 3.6 3.6 7.6-7.6L19 8z"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m1 10.4 4 2.3-.8 1.3L11 13V7h2z"/></svg>',
  alert: '<svg viewBox="0 0 24 24"><path d="M1 21h22L12 2zm12-3h-2v-2h2zm0-4h-2v-4h2z"/></svg>',
  tag: '<svg viewBox="0 0 24 24"><path d="M21.4 11.6 12.4 2.6A2 2 0 0 0 11 2H4a2 2 0 0 0-2 2v7c0 .55.22 1.05.59 1.42l9 9a2 2 0 0 0 2.82 0l7-7a2 2 0 0 0 0-2.82M6.5 8a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3"/></svg>',
};

function kpiCard({ label, value, unit, sub, icon, tone }) {
  return `<div class="kpi tone-${tone}">
    <div class="kpi-top"><span class="kpi-label">${label}</span><span class="kpi-icon">${ICONS[icon]}</span></div>
    <div class="kpi-value">${value}${unit ? `<small>${unit}</small>` : ""}</div>
    <div class="kpi-sub">${sub || "&nbsp;"}</div>
  </div>`;
}

function barChart(el, rows, { alt = false, unit = "" } = {}) {
  const max = Math.max(1, ...rows.map((r) => Number(r.value) || 0));
  el.innerHTML = rows.map((r) => `
    <div class="bar-row" title="${esc(r.label)}">
      <span class="bar-label">${esc(r.label)}</span>
      <div class="bar-track"><div class="bar-fill ${alt ? "alt" : ""}" data-w="${((Number(r.value) || 0) / max) * 100}"></div></div>
      <span class="bar-value ${r.value ? "" : "bar-empty"}">${r.value ? fmt(r.value) + unit : "بدون فروش"}</span>
    </div>`).join("");
  requestAnimationFrame(() => $$(".bar-fill", el).forEach((b) => (b.style.width = b.dataset.w + "%")));
}

function donut(el, parts, centerTop, centerBottom) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  const r = 70, c = 2 * Math.PI * r;
  let offset = 0;
  const circles = parts.map((p) => {
    const len = (p.value / total) * c;
    const svg = `<circle r="${r}" cx="95" cy="95" stroke="${p.color}" stroke-dasharray="0 ${c}" data-dash="${len} ${c - len}" stroke-dashoffset="${-offset}"></circle>`;
    offset += len;
    return svg;
  }).join("");
  el.innerHTML = `
    <div class="donut">
      <svg viewBox="0 0 190 190"><circle r="${r}" cx="95" cy="95" stroke="#EFECE3"></circle>${circles}</svg>
      <div class="donut-center"><strong>${centerTop}</strong><span>${centerBottom}</span></div>
    </div>
    <div class="legend">${parts.map((p) => `
      <div class="legend-item">
        <span class="legend-swatch" style="background:${p.color}"></span>
        <span>${esc(p.label)}</span><b>${faDigits(Math.round((p.value / total) * 100))}٪</b>
        <span class="muted">${fmt(p.value)} م.ر • ${fmt(p.count)} فاکتور</span>
      </div>`).join("")}
    </div>`;
  requestAnimationFrame(() => $$("circle[data-dash]", el).forEach((ci) => ci.setAttribute("stroke-dasharray", ci.dataset.dash)));
}

function renderTable(el, columns, rows, { onRowClick, cellRender, empty = "داده‌ای برای نمایش وجود ندارد" } = {}) {
  if (!rows.length) {
    el.innerHTML = `<div class="empty-state">${empty}</div>`;
    return;
  }
  el.innerHTML = `<table><thead><tr>${columns.map((c) => `<th>${esc(c.title)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r, i) => `<tr data-i="${i}" class="${onRowClick ? "clickable" : ""}">${columns.map((c) => cellRender ? cellRender(c, r) : defaultCell(c.key, r[c.key])).join("")}</tr>`).join("")}</tbody></table>`;
  if (onRowClick) $$("tbody tr", el).forEach((tr) => tr.addEventListener("click", () => onRowClick(rows[tr.dataset.i])));
}

function defaultCell(key, value) {
  if (key === "payment_status" && STATE.meta.status_labels[value]) return `<td>${statusPill(value)}</td>`;
  if (key === "invoice_number" || key === "sku_code") return `<td class="code">${esc(value)}</td>`;
  if (typeof value === "number") return `<td class="num">${fmt(value)}</td>`;
  return `<td>${esc(value ?? "—")}</td>`;
}

async function loadDashboard(force = false) {
  if (!force && STATE.cache.dashboard) return;
  $("#kpi-grid").innerHTML = Array(6).fill('<div class="kpi skeleton" style="height:132px"></div>').join("");
  try {
    const d = await api("/api/dashboard");
    STATE.cache.dashboard = d;
    const k = d.kpi;
    $("#kpi-grid").innerHTML = [
      kpiCard({ label: "فروش خالص کل", value: fmt(k.total_net), unit: "م.ر", sub: `${fmt(k.invoice_count)} فاکتور ثبت‌شده`, icon: "money", tone: "blue" }),
      kpiCard({ label: "تسویه‌شده", value: fmt(k.paid.amount), unit: "م.ر", sub: `${fmt(k.paid.count)} فاکتور`, icon: "check", tone: "green" }),
      kpiCard({ label: "چک در جریان", value: fmt(k.cheque_pending.amount), unit: "م.ر", sub: `${fmt(k.cheque_pending.count)} فاکتور`, icon: "clock", tone: "amber" }),
      kpiCard({ label: "مطالبات معوق", value: fmt(k.overdue.amount), unit: "م.ر", sub: `${fmt(k.overdue.count)} فاکتور`, icon: "alert", tone: "red" }),
      kpiCard({ label: "مجموع تخفیف‌ها", value: fmt(k.total_discount), unit: "م.ر", sub: `${fmt(k.customers)} مشتری • ${fmt(k.products)} محصول`, icon: "tag", tone: "violet" }),
    ].join("");

    barChart($("#chart-branch"), d.by_branch);
    barChart($("#chart-brand"), d.by_brand, { alt: true });
    donut($("#chart-status"), [
      { label: d.status_labels.PAID, value: k.paid.amount, count: k.paid.count, color: "#1F2839" },
      { label: d.status_labels.CHEQUE_PENDING, value: k.cheque_pending.amount, count: k.cheque_pending.count, color: "#B69D74" },
      { label: d.status_labels.OVERDUE, value: k.overdue.amount, count: k.overdue.count, color: "#B4483E" },
    ], fmt(k.total_net), "میلیون ریال");

    $("#reps-list").innerHTML = d.top_reps.map((r, i) => {
      const pct = r.target ? (r.value / r.target) * 100 : 0;
      return `<div class="list-item">
        <span class="avatar" style="background:${PALETTE[i % PALETTE.length]}">${esc(initials(r.label))}</span>
        <div class="list-main"><strong>${esc(r.label)}</strong><span>${esc(r.branch || "")} • ${faDigits(pct.toFixed(1))}٪ از تارگت</span>
          <div class="progress"><div data-w="${Math.min(pct, 100)}" style="background:${pct >= 100 ? "#3F7D5C" : pct >= 50 ? "#1F2839" : "#B69D74"}"></div></div>
        </div>
        <span class="list-val">${fmt(r.value)}</span>
      </div>`;
    }).join("");
    requestAnimationFrame(() => $$("#reps-list .progress > div").forEach((p) => (p.style.width = p.dataset.w + "%")));

    $("#customers-list").innerHTML = d.top_customers.map((c, i) => `
      <div class="list-item">
        <span class="avatar" style="background:${PALETTE[(i + 3) % PALETTE.length]}">${faDigits(i + 1)}</span>
        <div class="list-main"><strong title="${esc(c.label)}">${esc(c.label)}</strong><span>${esc(c.sector || "")} • ${fmt(c.count)} فاکتور</span></div>
        <span class="list-val">${fmt(c.value)}</span>
      </div>`).join("");

    renderTable($("#recent-table"), [
      { key: "invoice_number", title: "شماره فاکتور" }, { key: "invoice_date_fa", title: "تاریخ" },
      { key: "company_name", title: "مشتری" }, { key: "branch_name", title: "شعبه" },
      { key: "net_amount_m_rial", title: "مبلغ خالص (م.ر)" }, { key: "payment_status", title: "وضعیت" },
    ], d.recent_invoices, { onRowClick: (r) => openInvoice(r.invoice_id) });
  } catch (e) {
    $("#kpi-grid").innerHTML = `<div class="card empty-state">خطا در دریافت داشبورد: ${esc(e.message)}</div>`;
  }
}

/* ================= Invoices ================= */
const INV_COLUMNS = [
  { key: "invoice_number", title: "شماره فاکتور" },
  { key: "invoice_date_fa", title: "تاریخ صدور" },
  { key: "due_date_fa", title: "سررسید" },
  { key: "company_name", title: "مشتری" },
  { key: "branch_name", title: "شعبه" },
  { key: "sales_rep", title: "نماینده فروش" },
  { key: "item_count", title: "اقلام" },
  { key: "total_amount_m_rial", title: "مبلغ کل (م.ر)" },
  { key: "discount_m_rial", title: "تخفیف (م.ر)" },
  { key: "net_amount_m_rial", title: "خالص (م.ر)" },
  { key: "payment_status", title: "وضعیت" },
  { key: "payment_method", title: "روش پرداخت" },
];

async function loadInvoices(force = false) {
  if (force || !STATE.cache.invoices) {
    $("#inv-table").innerHTML = '<div class="skeleton" style="height:320px"></div>';
    try {
      STATE.cache.invoices = (await api("/api/web/invoices")).invoices;
    } catch (e) {
      $("#inv-table").innerHTML = `<div class="empty-state">خطا: ${esc(e.message)}</div>`;
      return;
    }
  }
  renderInvoiceFilters();
  renderInvoices();
}

function renderInvoiceFilters() {
  const all = STATE.cache.invoices;
  const opts = [["ALL", "همه"], ...Object.entries(STATE.meta.status_labels)];
  $("#inv-filter").innerHTML = opts.map(([code, label]) => {
    const n = code === "ALL" ? all.length : all.filter((i) => i.payment_status === code).length;
    return `<button data-code="${code}" class="${STATE.invFilter === code ? "active" : ""}">${esc(label)}<span class="count">${faDigits(n)}</span></button>`;
  }).join("");
  $$("#inv-filter button").forEach((b) => b.addEventListener("click", () => {
    STATE.invFilter = b.dataset.code;
    renderInvoiceFilters();
    renderInvoices();
  }));
}

function renderInvoices() {
  const q = $("#inv-search").value.trim().toLowerCase();
  const rows = STATE.cache.invoices.filter((r) =>
    (STATE.invFilter === "ALL" || r.payment_status === STATE.invFilter) &&
    (!q || [r.invoice_number, r.company_name, r.branch_name, r.sales_rep, r.payment_method, String(r.invoice_id)]
      .some((v) => String(v ?? "").toLowerCase().includes(q))));
  const sum = (k) => rows.reduce((s, r) => s + (Number(r[k]) || 0), 0);
  $("#inv-summary").innerHTML = `
    <span>تعداد: <b>${fmt(rows.length)}</b> فاکتور</span>
    <span>مبلغ کل: <b>${fmt(sum("total_amount_m_rial"))}</b> م.ر</span>
    <span>تخفیف: <b>${fmt(sum("discount_m_rial"))}</b> م.ر</span>
    <span>خالص: <b>${fmt(sum("net_amount_m_rial"))}</b> م.ر</span>`;
  renderTable($("#inv-table"), INV_COLUMNS, rows, {
    onRowClick: (r) => openInvoice(r.invoice_id),
    empty: "فاکتوری با این مشخصات پیدا نشد",
  });
}

async function openInvoice(id) {
  $("#drawer-title").textContent = "…";
  $("#drawer-body").innerHTML = '<div class="skeleton" style="height:240px"></div>';
  $("#drawer").classList.add("open");
  $("#drawer-backdrop").classList.add("open");
  try {
    const { invoice: inv, items } = await api(`/api/web/invoices/${id}`);
    $("#drawer-title").textContent = inv.invoice_number;
    const detail = (label, value) => `<div class="detail"><span>${label}</span><b>${value}</b></div>`;
    $("#drawer-body").innerHTML = `
      <div class="detail-grid">
        ${detail("مشتری", esc(inv.company_name))}
        ${detail("وضعیت پرداخت", statusPill(inv.payment_status))}
        ${detail("تاریخ صدور", esc(faDigits(inv.invoice_date_fa)))}
        ${detail("سررسید", esc(faDigits(inv.due_date_fa)))}
        ${detail("شعبه", esc(inv.branch_name))}
        ${detail("نماینده فروش", esc(inv.sales_rep))}
        ${detail("روش پرداخت", esc(inv.payment_method))}
        ${detail("شناسه فاکتور", fmt(inv.invoice_id))}
      </div>
      <div class="card-head"><h3>اقلام فاکتور</h3><span class="muted">${fmt(items.length)} قلم</span></div>
      <div class="table-wrap" id="drawer-items"></div>
      <div class="totals">
        <div><span>مبلغ کل</span><b>${fmt(inv.total_amount_m_rial)} م.ر</b></div>
        <div><span>تخفیف</span><b>${fmt(inv.discount_m_rial)} م.ر</b></div>
        <div class="grand"><span>مبلغ خالص</span><span>${fmt(inv.net_amount_m_rial)} م.ر</span></div>
      </div>`;
    renderTable($("#drawer-items"), [
      { key: "sku_code", title: "کد کالا" }, { key: "product_name", title: "کالا" }, { key: "brand", title: "برند" },
      { key: "quantity", title: "تعداد" }, { key: "unit_price_m_rial", title: "فی (م.ر)" }, { key: "line_total_m_rial", title: "جمع (م.ر)" },
    ], items, { empty: "این فاکتور قلمی ندارد" });
  } catch (e) {
    $("#drawer-body").innerHTML = `<div class="empty-state">خطا: ${esc(e.message)}</div>`;
  }
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer-backdrop").classList.remove("open");
}

/* ================= Raw tables ================= */
async function loadTables(force = false) {
  if (force || !STATE.cache.tablesMeta) {
    try {
      STATE.cache.tablesMeta = await api("/api/tables");
    } catch (e) {
      $("#raw-table").innerHTML = `<div class="empty-state">خطا: ${esc(e.message)}</div>`;
      return;
    }
  }
  const metas = STATE.cache.tablesMeta;
  STATE.currentTable = STATE.currentTable || metas[0].name;
  $("#table-tabs").innerHTML = metas.map((t) => `
    <button class="table-tab ${t.name === STATE.currentTable ? "active" : ""}" data-name="${t.name}">
      <strong>${esc(t.title)}</strong><span class="ltr">${t.name}</span><span>${fmt(t.rows)} ردیف</span>
    </button>`).join("");
  $$(".table-tab").forEach((b) => b.addEventListener("click", () => {
    STATE.currentTable = b.dataset.name;
    $("#table-search").value = "";
    loadTables();
  }));
  await showTable(STATE.currentTable, force);
}

async function showTable(name, force = false) {
  const key = `table:${name}`;
  if (force || !STATE.cache[key]) {
    $("#raw-table").innerHTML = '<div class="skeleton" style="height:320px"></div>';
    STATE.cache[key] = await api(`/api/tables/${name}`);
  }
  renderRawTable();
}

function renderRawTable() {
  const t = STATE.cache[`table:${STATE.currentTable}`];
  if (!t) return;
  const q = $("#table-search").value.trim().toLowerCase();
  const rows = q ? t.rows.filter((r) => Object.values(r).some((v) => String(v ?? "").toLowerCase().includes(q))) : t.rows;
  $("#table-title").textContent = t.title;
  $("#table-count").textContent = `${fmt(rows.length)} از ${fmt(t.rows.length)} ردیف • ${fmt(t.columns.length)} ستون`;
  renderTable($("#raw-table"), t.columns, rows, {
    cellRender: (c, r) => {
      const v = r[c.key];
      if (c.key === "payment_status") {
        const code = Object.keys(STATE.meta.status_labels).find((k) => STATE.meta.status_labels[k] === v);
        return `<td>${code ? statusPill(code) : esc(v)}</td>`;
      }
      if (/_id$/.test(c.key) && typeof v === "number") return `<td>${faDigits(v)}</td>`;
      return defaultCell(c.key, v);
    },
    empty: "ردیفی با این جستجو پیدا نشد",
  });
}

/* ================= Chat ================= */
const SUGGESTIONS = [
  "فاکتورهای معوق را نشان بده",
  "مجموع فروش خالص هر شعبه چقدر است؟",
  "کدام نماینده بیشترین فروش را داشته است؟",
  "سقف اعتبار شرکت مپنا (توگا) چقدر است؟",
  "کران‌سا نماینده کدام برندهای خارجی است؟",
  "وضعیت فاکتور KRS-1405-802 را تسویه‌شده کن",
];
const INTENT_FA = {
  view_data: "پایگاه داده",
  modify_data: "ویرایش داده",
  document_question: "اسناد شرکت",
  hybrid: "ترکیبی",
  greeting: "گفتگو",
};
const BOT_ICON = '<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h4a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3v-8a3 3 0 0 1 3-3h4V5.73A2 2 0 0 1 12 2M9 12a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3m6 0a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3"/></svg>';
const HISTORY_KEY = "krs-chat-history";

function inline(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, '<code class="ltr">$1</code>');
}

function parseMdTable(lines) {
  const cells = (l) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
  const body = lines.filter((l) => !/^\|?\s*:?-{2,}/.test(l.trim()));
  const [head, ...rows] = body.map(cells);
  return { head, rows };
}

function mdTableHtml(lines) {
  const { head, rows } = parseMdTable(lines);
  if (!head) return "";
  const isNum = (v) => /^-?[\d.,]+$/.test(v);
  return `<div class="table-wrap"><table><thead><tr>${head.map((h) => `<th>${esc(colTitle(h))}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((v, i) => {
      if (head[i] === "payment_status" && STATE.meta.status_labels[v]) return `<td>${statusPill(v)}</td>`;
      if (/^KRS-/.test(v)) return `<td class="code">${esc(v)}</td>`;
      if (isNum(v)) return `<td class="num">${fmt(Number(v.replace(/,/g, "")))}</td>`;
      return `<td>${esc(v)}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function renderMarkdown(text) {
  const lines = String(text ?? "").split(/\r?\n/);
  const out = [];
  let para = [], list = null, table = [];
  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join("<br>"))}</p>`); para = []; } };
  const flushList = () => { if (list) { out.push(`<${list.type}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.type}>`); list = null; } };
  const flushTable = () => { if (table.length) { out.push(mdTableHtml(table)); table = []; } };

  for (const raw of lines) {
    if (raw.trim().startsWith("|")) { flushPara(); flushList(); table.push(raw.trim()); continue; }
    flushTable();
    const line = esc(raw.trim());
    if (!line) { flushPara(); flushList(); continue; }
    const h = line.match(/^#{1,6}\s+(.*)$/);
    const ul = line.match(/^[-*•]\s+(.*)$/);
    const ol = line.match(/^[0-9۰-۹]+[.)]\s+(.*)$/);
    if (h) { flushPara(); flushList(); out.push(`<h4>${inline(h[1])}</h4>`); }
    else if (ul || ol) {
      flushPara();
      const type = ul ? "ul" : "ol";
      if (!list || list.type !== type) { flushList(); list = { type, items: [] }; }
      list.items.push((ul || ol)[1]);
    } else { flushList(); para.push(line.startsWith("⛔") ? `<span class="rls">${line}</span>` : line); }
  }
  flushPara(); flushList(); flushTable();
  return out.join("");
}

function scrollChat() {
  const body = $("#chat-body");
  body.scrollTop = body.scrollHeight;
}

function addUserMessage(text) {
  $("#welcome").style.display = "none";
  const el = document.createElement("div");
  el.className = "msg msg-user";
  el.innerHTML = `<div class="who">شما</div><div class="bubble">${esc(text)}</div>`;
  $("#chat-body").appendChild(el);
  scrollChat();
}

function addBotMessage(msg) {
  $("#welcome").style.display = "none";
  const el = document.createElement("div");
  el.className = "msg msg-bot";
  if (msg.pending) {
    el.innerHTML = `<div class="who">${BOT_ICON}</div><div class="bubble-wrap"><div class="bubble">
      <span class="typing"><span></span><span></span><span></span></span><span class="typing-text">در حال آماده‌سازی پاسخ…</span>
    </div></div>`;
  } else {
    const table = msg.table_md && msg.table_md.trim().startsWith("|") ? mdTableHtml(msg.table_md.split("\n").filter((l) => l.trim().startsWith("|"))) : "";
    el.innerHTML = `<div class="who">${BOT_ICON}</div><div class="bubble-wrap">
      <div class="bubble ${msg.error ? "error" : ""}">${renderMarkdown(msg.answer)}${table}</div>
      <div class="msg-meta">
        ${msg.intent ? `<span class="tag tag-${msg.intent}">${INTENT_FA[msg.intent] || msg.intent}</span>` : ""}
        ${msg.data_changed ? '<span class="tag tag-modify_data">داده‌ها به‌روزرسانی شد</span>' : ""}
        <button class="meta-btn copy-btn" title="کپی پاسخ"><svg viewBox="0 0 24 24"><path d="M16 1H4a2 2 0 0 0-2 2v14h2V3h12zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m0 16H8V7h11z"/></svg>کپی</button>
      </div></div>`;
    $(".copy-btn", el).addEventListener("click", async () => {
      await navigator.clipboard.writeText(msg.answer);
      toast("پاسخ کپی شد");
    });
  }
  $("#chat-body").appendChild(el);
  scrollChat();
  return el;
}

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; } catch { return []; }
}
function saveHistory(history) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-60)));
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || STATE.busy) return;
  STATE.busy = true;
  $("#send-btn").disabled = true;
  const input = $("#chat-input");
  input.value = "";
  autoGrow();

  const history = loadHistory();
  history.push({ role: "user", text });
  addUserMessage(text);
  const pending = addBotMessage({ pending: true });

  let msg;
  try {
    const res = await api("/api/chat", { method: "POST", body: JSON.stringify({ message: text }) });
    msg = { answer: res.answer, intent: res.intent, table_md: res.table_md, data_changed: res.data_changed };
    if (res.data_changed) {
      STATE.cache = {};
      toast("فاکتورها به‌روزرسانی شدند");
    }
  } catch (e) {
    msg = { answer: `خطا در دریافت پاسخ: ${e.message}`, error: true };
  }
  pending.remove();
  addBotMessage(msg);
  history.push({ role: "bot", ...msg });
  saveHistory(history);
  STATE.busy = false;
  $("#send-btn").disabled = false;
  input.focus();
}

function restoreChat() {
  const history = loadHistory();
  history.forEach((m) => (m.role === "user" ? addUserMessage(m.text) : addBotMessage(m)));
}

function clearChat() {
  localStorage.removeItem(HISTORY_KEY);
  $$("#chat-body .msg").forEach((m) => m.remove());
  $("#welcome").style.display = "";
}

function autoGrow() {
  const ta = $("#chat-input");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
}

/* ================= Init ================= */
async function checkHealth() {
  try {
    await api("/health");
    $("#health-dot").className = "status-dot ok";
    $("#health-text").textContent = "متصل به سرور";
  } catch {
    $("#health-dot").className = "status-dot bad";
    $("#health-text").textContent = "عدم اتصال به سرور";
  }
}

async function init() {
  const dateParts = Object.fromEntries(
    new Intl.DateTimeFormat("fa-IR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
      .formatToParts(new Date()).map((p) => [p.type, p.value]),
  );
  $("#today-chip").textContent = `${dateParts.weekday}، ${dateParts.day} ${dateParts.month} ${dateParts.year}`;

  $("#suggestions").innerHTML = SUGGESTIONS.map((s) => `
    <button class="suggestion" type="button"><svg viewBox="0 0 24 24"><path d="M12 2l2.4 5.6L20 10l-5.6 2.4L12 18l-2.4-5.6L4 10l5.6-2.4z"/></svg><span>${esc(s)}</span></button>`).join("");
  $$(".suggestion").forEach((b) => b.addEventListener("click", () => sendMessage(b.textContent)));

  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); sendMessage($("#chat-input").value); });
  $("#chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(e.target.value); }
  });
  $("#chat-input").addEventListener("input", autoGrow);
  $("#clear-chat").addEventListener("click", clearChat);

  $("#inv-search").addEventListener("input", () => STATE.cache.invoices && renderInvoices());
  $("#table-search").addEventListener("input", renderRawTable);

  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#drawer-backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeDrawer());
  $("#menu-btn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));

  $("#refresh-btn").addEventListener("click", async () => {
    const btn = $("#refresh-btn");
    btn.classList.add("spinning");
    STATE.cache = {};
    const view = (location.hash || "#dashboard").slice(1);
    try {
      if (view === "invoices") await loadInvoices(true);
      else if (view === "tables") await loadTables(true);
      else await loadDashboard(true);
      toast("داده‌ها به‌روزرسانی شد");
    } finally {
      btn.classList.remove("spinning");
    }
  });

  try { STATE.meta = await api("/api/meta"); } catch { /* keep defaults */ }
  restoreChat();
  checkHealth();
  window.addEventListener("hashchange", route);
  route();
}

init();
