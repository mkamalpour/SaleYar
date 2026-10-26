"use strict";
const $ = (id) => document.getElementById(id);
const safeStore = {
  get(k) {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem(k, v);
    } catch {}
  },
  remove(k) {
    try {
      localStorage.removeItem(k);
    } catch {}
  },
};
let runtime = {};
try {
  runtime = JSON.parse($("saleyar-runtime").textContent);
} catch {}
let apiBase =
    runtime.apiBase ||
    safeStore.get("saleYar_apiBase") ||
    (location.protocol === "file:" ? "http://127.0.0.1:8000" : location.origin),
  apiKey = runtime.apiKey || "",
  llmMode = safeStore.get("saleYar_llmMode") || "keyword",
  talkMode = safeStore.get("saleYar_talkMode") !== "false";
safeStore.remove("saleYar_apiKey");
let report = null,
  inventory = {},
  currentTab = "overview",
  searchTerm = "",
  page = 1,
  language = "en",
  analysisController = null;
const pageSize = 40;
const tabs = {
  overview: ["Overview", "نمای کلی", "▦"],
  orders: ["Purchase orders", "سفارش خرید", "↗"],
  forecast: ["Demand forecast", "پیش‌بینی تقاضا", "▥"],
  products: ["Products", "محصولات", "□"],
  segments: ["Product segments", "دسته‌بندی محصولات", "◇"],
  basket: ["Basket rules", "سبد خرید", "⇄"],
  inventory: ["Inventory", "موجودی", "▤"],
  customers: ["Customers & ROI", "مشتریان و بازده", "◎"],
  settings: ["Settings", "تنظیمات", "⚙"],
};
const fa = {
  workspace: "فضای کار فروشگاه",
  local: "فروشگاه شما. تصمیم شما.",
  intelligence: "هوشمندی فروشگاه",
  shop: "شناسه فروشگاه",
  budget: "بودجه (تومان)",
  goal: "هدف بهینه‌سازی",
  language: "زبان",
  upload: "بارگذاری فایل فروش",
  formats: "CSV / Excel · تحلیل محلی",
  advisor: "مشاور فروشگاه",
  advisorHint: "پاسخ بر اساس تحلیل شما",
  send: "ارسال",
  analyzing: "در حال تحلیل فروشگاه",
  wait: "در حال تهیه پیشنهادها. می‌توانید انتظار را لغو کنید.",
  cancel: "لغو",
};
const en = Object.fromEntries(
  [...document.querySelectorAll("[data-i18n]")].map((e) => [
    e.dataset.i18n,
    e.textContent,
  ]),
);
const translationPairs = new Map();
const t = (en, fa) => {
  translationPairs.set(en, [en, fa]);
  translationPairs.set(fa, [en, fa]);
  return language === "fa" ? fa : en;
};
let statusPair = [
  "Ready to analyze",
  "\u0622\u0645\u0627\u062f\u0647 \u062a\u062d\u0644\u06cc\u0644",
];
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const num = (v, d = 0) =>
  v === null || v === undefined || v === "" || !Number.isFinite(Number(v))
    ? "—"
    : Number(v).toLocaleString(language === "fa" ? "fa-IR" : "en-US", {
        maximumFractionDigits: d,
      });
const n = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
const getProducts = () =>
  Array.isArray(report?.products) ? report.products : [];
const getOrders = () =>
  Array.isArray(report?.purchase_order)
    ? report.purchase_order
    : Array.isArray(report?.order)
      ? report.order
      : [];
const getBasketRules = () =>
  Array.isArray(report?.basket_rules) ? report.basket_rules : [];
const getCustomers = () => report?.customers || {};
const filtered = (items) =>
  items.filter((p) =>
    String(p.product ?? "")
      .toLocaleLowerCase()
      .includes(searchTerm),
  );
function status(text) {
  statusPair = [text, text];
  for (const [value, pair] of translationPairs) {
    if (String(text).startsWith(value)) {
      const suffix = String(text).slice(value.length);
      statusPair = pair.map((v) => v + suffix);
      break;
    }
  }
  $("status").textContent = statusPair[language === "fa" ? 1 : 0];
}
function empty(title, detail) {
  return `<div class="empty"><div class="empty-icon" aria-hidden="true">↥</div><h2>${esc(title)}</h2><p>${esc(detail)}</p>${!report ? `<button class="primary" id="emptyUpload">${t("Choose sales file", "انتخاب فایل فروش")}</button><div class="steps"><span>01 · ${t("Upload sales", "بارگذاری فروش")}</span><span>02 · ${t("Review insights", "بررسی تحلیل")}</span><span>03 · ${t("Plan purchases", "برنامه خرید")}</span></div>` : ""}</div>`;
}
function stats(items) {
  return `<div class="stats-grid">${items.map(([label, value]) => `<div class="stat-card"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div></div>`).join("")}</div>`;
}
function table(headers, rows) {
  return `<div class="table-wrap" tabindex="0" role="region" aria-label="${esc(t("Scrollable data table", "\u062c\u062f\u0648\u0644 \u062f\u0627\u062f\u0647 \u0642\u0627\u0628\u0644 \u067e\u06cc\u0645\u0627\u06cc\u0634"))}"><table class="data-table ${headers.length > 4 ? "wide-table" : ""}"><thead><tr>${headers.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${(rows.length ? rows : [headers.map((_, i) => (i === 0 ? esc(t("No records available", "رکوردی موجود نیست")) : "—"))]).map((row) => `<tr>${row.map((v) => `<td>${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function badge(text, kind = "") {
  return `<span class="badge ${kind}">${esc(text)}</span>`;
}
function paged(items, headers, toRow) {
  if (!items.length)
    return empty(
      t("No matching records", "موردی یافت نشد"),
      t(
        "Try a different search, or upload more sales data.",
        "جست‌وجو را تغییر دهید یا داده فروش بیشتری بارگذاری کنید.",
      ),
    );
  const pages = Math.ceil(items.length / pageSize);
  page = Math.max(1, Math.min(page, pages));
  return (
    `<div class="pagination"><span>${num(items.length)} ${t("records", "رکورد")} · ${num((page - 1) * pageSize + 1)}–${num(Math.min(page * pageSize, items.length))}</span><div><button data-page="-1" ${page === 1 ? "disabled" : ""}>${t("Previous", "قبلی")}</button><span>${num(page)} / ${num(pages)}</span><button data-page="1" ${page === pages ? "disabled" : ""}>${t("Next", "بعدی")}</button></div></div>` +
    table(
      headers,
      items.slice((page - 1) * pageSize, page * pageSize).map(toRow),
    )
  );
}
function setLanguage() {
  language = $("lang").value;
  $("status").textContent = statusPair[language === "fa" ? 1 : 0];
  const welcome = $("advisorWelcome");
  if (welcome)
    welcome.textContent = t(
      "Welcome to SaleYar. Ask about your shop after uploading sales data.",
      "\u0628\u0647 SaleYar \u062e\u0648\u0634 \u0622\u0645\u062f\u06cc\u062f. \u067e\u0633 \u0627\u0632 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0641\u0631\u0648\u0634\u060c \u062f\u0631\u0628\u0627\u0631\u0647 \u0641\u0631\u0648\u0634\u06af\u0627\u0647 \u0628\u067e\u0631\u0633\u06cc\u062f.",
    );
  document.documentElement.lang = language;
  document.documentElement.dir = language === "fa" ? "rtl" : "ltr";
  document
    .querySelectorAll("[data-i18n]")
    .forEach(
      (e) =>
        (e.textContent =
          language === "fa" ? fa[e.dataset.i18n] : en[e.dataset.i18n]),
    );
  $("globalSearch").placeholder = t("Search products…", "جست‌وجوی محصولات…");
  $("globalSearch").setAttribute(
    "aria-label",
    t("Search products", "جست‌وجوی محصولات"),
  );
  $("llmInput").placeholder = t(
    "Ask about stock, orders or profit…",
    "درباره موجودی، سفارش یا سود بپرسید…",
  );
  [...$("goal").options].forEach(
    (o, i) =>
      (o.textContent = (
        language === "fa"
          ? ["بیشینه‌سازی سود", "پوشش مشتریان", "کاهش ریسک"]
          : ["Maximize profit", "Cover customers", "Reduce risk"]
      )[i]),
  );
  renderNav();
  renderCurrentTab();
}
function renderNav() {
  $("navigation").innerHTML = Object.entries(tabs)
    .map(
      ([key, v]) =>
        `<button class="nav-item ${key === currentTab ? "active" : ""}" data-tab="${key}" ${key === currentTab ? 'aria-current="page"' : ""}><span class="nav-icon" aria-hidden="true">${v[2]}</span><span>${v[language === "fa" ? 1 : 0]}</span></button>`,
    )
    .join("");
  $("pageTitle").textContent = tabs[currentTab][language === "fa" ? 1 : 0];
}
$("navigation").addEventListener("click", (e) => {
  const button = e.target.closest("[data-tab]");
  if (!button) return;
  currentTab = button.dataset.tab;
  page = 1;
  renderNav();
  renderCurrentTab();
});
$("globalSearch").addEventListener("input", (e) => {
  searchTerm = e.target.value.toLocaleLowerCase();
  page = 1;
  renderCurrentTab();
});
$("lang").addEventListener("change", setLanguage);
function renderCurrentTab() {
  const area = $("contentArea");
  if (currentTab === "settings") {
    renderSettings();
    return;
  }
  if (!report) {
    area.innerHTML = empty(
      t(
        "Make your next purchase a smarter one",
        "خرید بعدی را هوشمندانه‌تر انجام دهید",
      ),
      t(
        "Upload your sales CSV or Excel file to discover demand, stock risks and a purchase plan that fits your budget.",
        "فایل فروش را بارگذاری کنید تا تقاضا، ریسک موجودی و برنامه خرید متناسب با بودجه را ببینید.",
      ),
    );
    $("emptyUpload").onclick = () => $("fileInput").click();
    return;
  }
  const products = filtered(getProducts());
  let html = "";
  switch (currentTab) {
    case "overview": {
      const all = getProducts(),
        top = [...products]
          .sort((a, b) => n(b.total_revenue) - n(a.total_revenue))
          .slice(0, 5);
      html = stats([
        [
          t("Shop health", "سلامت فروشگاه"),
          report.health_score == null ? "—" : `${num(report.health_score)}/100`,
        ],
        [
          t("Revenue · Toman", "درآمد · تومان"),
          num(all.reduce((s, p) => s + n(p.total_revenue), 0)),
        ],
        [
          t("Profit · Toman", "سود · تومان"),
          num(all.reduce((s, p) => s + n(p.total_profit), 0)),
        ],
        [t("Products analyzed", "محصولات تحلیل‌شده"), num(all.length)],
      ]);
      const actions = Array.isArray(report.priority_actions)
        ? report.priority_actions
        : [];
      if (actions.length)
        html += `<section class="panel"><h3>${t("Your next moves", "اقدام‌های بعدی")}</h3>${actions.map((a) => `<div class="actions"><strong>${esc(a.title)}</strong><div class="subtle">${esc(a.description)}</div></div>`).join("")}</section>`;
      const urgent = filtered(getOrders()).filter(
        (o) =>
          n(o.qty) > 0 && o.current_stock != null && n(o.current_stock) === 0,
      );
      if (urgent.length)
        html +=
          `<section class="panel"><h3>${t("Restock now", "نیاز فوری به تأمین")}</h3>` +
          table(
            [
              t("Product", "محصول"),
              t("Buy quantity", "تعداد خرید"),
              t("Cost · Toman", "هزینه · تومان"),
            ],
            urgent.map((o) => [
              esc(o.product),
              num(o.qty),
              num(n(o.qty) * n(o.unit_cost)),
            ]),
          ) +
          "</section>";
      html +=
        `<section class="panel"><div class="panel-heading"><h3>${t("Revenue leaders", "پرفروش‌ترین محصولات")}</h3><span class="subtle">${t("Top 5 products", "۵ محصول برتر")}</span></div>` +
        table(
          [
            t("Product", "محصول"),
            t("Revenue · Toman", "درآمد · تومان"),
            t("Margin", "حاشیه سود"),
          ],
          top.map((p) => [
            esc(p.product),
            num(p.total_revenue),
            num(p.profit_margin, 1) + "%",
          ]),
        ) +
        "</section>";
      break;
    }
    case "orders": {
      const orders = filtered(getOrders());
      html =
        `<section class="panel"><div class="toolbar"><div><h3>${t("Recommended purchases", "خریدهای پیشنهادی")}</h3><p class="subtle">${t("Total cost", "هزینه کل")}: ${num(orders.reduce((s, o) => s + n(o.qty) * n(o.unit_cost), 0))} ${t("Toman", "تومان")}</p></div><div><button id="copyOrdersBtn">${t("Copy list", "کپی فهرست")}</button> <button id="exportOrdersBtn">${t("Export CSV", "خروجی CSV")}</button></div></div>` +
        paged(
          orders,
          [
            t("Product", "محصول"),
            t("Stock", "موجودی"),
            t("Buy", "خرید"),
            t("Unit cost", "هزینه واحد"),
            t("Total", "جمع"),
            t("Reason", "دلیل"),
          ],
          (o) => [
            esc(o.product),
            num(o.current_stock),
            num(o.qty),
            num(o.unit_cost),
            num(n(o.qty) * n(o.unit_cost)),
            esc(o.reason),
          ],
        ) +
        "</section>";
      break;
    }
    case "forecast":
      html = "<p>" + esc(t(
        "Local baselines stay low support even when a short holdout has small errors. Validation is not guaranteed accuracy. Missing sale days are treated as zero; incomplete invoice history can distort demand.",
        "\u0631\u0648\u0634 \u067e\u0627\u06cc\u0647 \u0645\u0634\u062e\u0635 \u0634\u062f\u0647 \u0627\u0633\u062a. \u0627\u0639\u062a\u0628\u0627\u0631\u0633\u0646\u062c\u06cc \u062a\u0636\u0645\u06cc\u0646 \u062f\u0642\u062a \u0646\u06cc\u0633\u062a. \u0631\u0648\u0632\u0647\u0627\u06cc \u0628\u062f\u0648\u0646 \u0641\u0631\u0648\u0634 \u0635\u0641\u0631 \u0641\u0631\u0636 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f\u061b \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u0646\u0627\u0642\u0635 \u0646\u062a\u06cc\u062c\u0647 \u0631\u0627 \u0645\u0646\u062d\u0631\u0641 \u0645\u06cc\u200c\u06a9\u0646\u062f."
      )) + "</p>" + paged(
        products.filter((p) => p.forecast),
        [
          t("Product", "محصول"),
          t("30-day demand", "تقاضای ۳۰ روز"),
          t("60 days", "۶۰ روز"),
          t("90 days", "۹۰ روز"),
          t("Validation support", "\u067e\u0634\u062a\u0648\u0627\u0646\u0647 \u0627\u0639\u062a\u0628\u0627\u0631\u0633\u0646\u062c\u06cc"),
          t("Holdout WAPE", "\u062e\u0637\u0627\u06cc \u062f\u0648\u0631\u0647 \u0622\u0632\u0645\u0648\u0646"),
          t('Holdout bias (+ overforecast)', 'سوگیری آزمون (+ بیش‌برآورد)'),
          t("Status / method", "\u0648\u0636\u0639\u06cc\u062a / \u0631\u0648\u0634"),
        ],
        (p) => [
          esc(p.product),
          p.forecast.skipped ? "\u2014" : num(p.forecast.h30),
          p.forecast.skipped ? "\u2014" : num(p.forecast.h60),
          p.forecast.skipped ? "\u2014" : num(p.forecast.h90),
          badge(p.forecast.skipped ? t("Unavailable", "\u062f\u0631 \u062f\u0633\u062a\u0631\u0633 \u0646\u06cc\u0633\u062a") : p.forecast.confidence || "\u2014"),
          typeof p.forecast.validation?.wape_percent === "number" ? num(p.forecast.validation.wape_percent, 1) + "%" : "\u2014",
          typeof p.forecast.validation?.bias_percent === 'number' ? num(p.forecast.validation.bias_percent, 1) + '%' : '\u2014',
          p.forecast.skipped ? esc(p.forecast.skip_reason || "No forecast generated") :
            esc(p.forecast.method || "\u2014") + (p.forecast.note ?
              `<details class="forecast-note"><summary>${esc(t("Details", "\u062c\u0632\u0626\u06cc\u0627\u062a"))}</summary><p>${esc(p.forecast.note)}</p>${p.forecast.data_end ? `<p>${esc(t("Data through", "\u062f\u0627\u062f\u0647 \u062a\u0627"))}: ${esc(p.forecast.data_end)}</p>` : ""}</details>` : ""),
        ],
      );
      break;
    case "products":
      html = paged(
        products,
        [
          t("Rank", "رتبه"),
          t("Product", "محصول"),
          t("Segment", "دسته"),
          t("Revenue · Toman", "درآمد · تومان"),
          t("Margin", "حاشیه سود"),
          t("Risk", "ریسک"),
          t("Days since sale", "روز از آخرین فروش"),
        ],
        (p, i) => [
          num(p.rank ?? (page - 1) * pageSize + i + 1),
          esc(p.product),
          badge(
            p.segment || "Individual",
            p.segment === "Star"
              ? "badge-success"
              : p.segment === "Deadweight"
                ? "badge-danger"
                : "",
          ),
          num(p.total_revenue),
          num(p.profit_margin, 1) + "%",
          num(p.risk_score),
          num(p.days_since_last_sale),
        ],
      );
      break;
    case "segments": {
      const groups = new Map();
      products.forEach((p) => {
        const k = p.segment || "Individual";
        groups.set(k, (groups.get(k) || 0) + 1);
      });
      html =
        stats([...groups].map(([k, v]) => [k, num(v)])) +
        paged(products, [t("Product", "محصول"), t("Segment", "دسته")], (p) => [
          esc(p.product),
          badge(p.segment || "Individual"),
        ]);
      break;
    }
    case "basket":
      html = paged(
        getBasketRules().filter((r) =>
          JSON.stringify([r.antecedent, r.consequent])
            .toLocaleLowerCase()
            .includes(searchTerm),
        ),
        [
          t("Bought together", "خرید اول"),
          t("Also bought", "خرید همراه"),
          t("Confidence", "اطمینان"),
          t("Lift", "ضریب همراهی"),
        ],
        (r) => [
          esc((r.antecedent || []).join(" + ")),
          esc((r.consequent || []).join(" + ")),
          num(r.confidence == null ? null : n(r.confidence) * 100, 1) + "%",
          num(r.lift, 2),
        ],
      );
      break;
    case "inventory": {
      const inv = Object.entries(inventory).filter(([p]) =>
        p.toLocaleLowerCase().includes(searchTerm),
      );
      html =
        stats([
          [
            t("Out of stock", "ناموجود"),
            num(inv.filter(([, q]) => q != null && n(q) === 0).length),
          ],
          [
            t("Low stock · under 20", "موجودی کم · زیر ۲۰"),
            num(
              inv.filter(([, q]) => q != null && n(q) > 0 && n(q) < 20).length,
            ),
          ],
        ]) +
        paged(
          inv,
          [t("Product", "محصول"), t("Stock", "موجودی"), t("Status", "وضعیت")],
          ([p, q]) => [
            esc(p),
            num(q),
            q == null
              ? badge(t("Unknown", "نامشخص"))
              : n(q) === 0
                ? badge(t("Out of stock", "ناموجود"), "badge-danger")
                : n(q) < 20
                  ? badge(t("Low stock", "کم"), "badge-warning")
                  : badge(t("In stock", "موجود"), "badge-success"),
          ],
        );
      break;
    }
    case "customers": {
      const c = getCustomers();
      html =
        stats(Object.entries(c.summary || {}).map(([k, v]) => [k, num(v)])) +
        `<section class="panel"><h3>${t("Return on investment", "بازده سرمایه‌گذاری")}</h3><p>${t("Shop ROI", "بازده فروشگاه")}: <strong>${num(report.shop_roi, 1)}%</strong></p><p class="subtle">${t("Difference from bank benchmark (23%)", "اختلاف با معیار بانکی (۲۳٪)")}: ${num(report.vs_bank, 1)} ${t("percentage points", "واحد درصد")}</p></section><section class="panel"><h3>${t("Champion products", "محصولات مشتریان برتر")}</h3>${(c.champion_products || []).length ? `<ul>${c.champion_products.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : `<p class="subtle">${t("No champion products identified yet.", "هنوز محصولی شناسایی نشده است.")}</p>`}</section>`;
      break;
    }
  }
  area.innerHTML = html;
  area.querySelectorAll("[data-page]").forEach(
    (b) =>
      (b.onclick = () => {
        page += Number(b.dataset.page);
        renderCurrentTab();
        $("contentArea").focus();
      }),
  );
  if ($("copyOrdersBtn"))
    $("copyOrdersBtn").onclick = async () => {
      try {
        await navigator.clipboard.writeText(
          filtered(getOrders())
            .map((o) => `${o.product}: ${o.qty}`)
            .join("\n"),
        );
        status(t("Purchase list copied", "فهرست خرید کپی شد"));
      } catch {
        status(
          t(
            "Copy unavailable. Use Export CSV instead.",
            "کپی در دسترس نیست؛ خروجی CSV بگیرید.",
          ),
        );
      }
    };
  if ($("exportOrdersBtn")) $("exportOrdersBtn").onclick = exportOrders;
}
function csvCell(v) {
  let value = String(v ?? "");
  if (/^[\s]*[=+@\-]/.test(value)) value = "'" + value;
  return '"' + value.replace(/"/g, '""') + '"';
}
function exportOrders() {
  const rows = [
    ["Product", "Stock", "Buy", "Unit Cost", "Total", "Reason"],
    ...filtered(getOrders()).map((o) => [
      o.product,
      o.current_stock,
      o.qty,
      o.unit_cost,
      n(o.qty) * n(o.unit_cost),
      o.reason,
    ]),
  ];
  const url = URL.createObjectURL(
    new Blob(
      ["\uFEFF" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n")],
      { type: "text/csv;charset=utf-8" },
    ),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "saleyar-purchase-orders.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function renderSettings() {
  $("contentArea").innerHTML =
    `<section class="panel settings"><h2>${t("Connection & advisor", "اتصال و مشاور")}</h2><p class="subtle">${t("Your API key stays in memory for this session. Sales files are sent only to this API.", "کلید API تنها در حافظه این نشست نگهداری می‌شود. فایل فروش فقط به این API ارسال می‌شود.")}</p><form id="settingsForm"><label for="setApiUrl">${t("API base URL", "نشانی پایه API")}<input id="setApiUrl" type="url" required></label><label for="setApiKey">${t("API key", "کلید API")}<input id="setApiKey" type="password" autocomplete="off"></label><label for="llmModeSelect">${t("Advisor mode", "حالت مشاور")}<select id="llmModeSelect"><option value="keyword">${t("Local keyword advisor · offline", "مشاور محلی · آفلاین")}</option><option value="real">${t("Language model · requires backend", "مدل زبانی · نیازمند سرور")}</option></select></label><label class="check"><input id="talkModeCheckbox" type="checkbox">${t("Short conversational answers", "پاسخ کوتاه و محاوره‌ای")}</label><button class="primary" id="saveSettingsBtn">${t("Save settings", "ذخیره تنظیمات")}</button></form></section>`;
  $("setApiUrl").value = apiBase;
  $("setApiKey").value = apiKey;
  $("llmModeSelect").value = llmMode;
  $("talkModeCheckbox").checked = talkMode;
  $("settingsForm").onsubmit = (e) => {
    e.preventDefault();
    try {
      const url = new URL($("setApiUrl").value);
      if (
        !["http:", "https:"].includes(url.protocol) ||
        url.username ||
        url.password ||
        url.search ||
        url.hash
      )
        throw new Error("Use a plain HTTP or HTTPS API URL");
      apiBase = url.href.replace(/\/$/, "");
      apiKey = $("setApiKey").value.trim();
      llmMode = $("llmModeSelect").value;
      talkMode = $("talkModeCheckbox").checked;
      safeStore.set("saleYar_apiBase", apiBase);
      safeStore.set("saleYar_llmMode", llmMode);
      safeStore.set("saleYar_talkMode", String(talkMode));
      status(t("Settings saved for this session", "تنظیمات نشست ذخیره شد"));
    } catch (err) {
      status(err.message);
    }
  };
}
async function request(path, options = {}, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(abort, 30000);
  try {
    const response = await fetch(apiBase.replace(/\/$/, "") + path, {
      ...options,
      headers: { "X-API-Key": apiKey, ...options.headers },
      signal: controller.signal,
    });
    if (!response.ok) {
      const error = new Error(
        `HTTP ${response.status}: ${response.status === 401 ? "Check your API key in Settings." : response.statusText || "Request failed"}`,
      );
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}
function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Cancelled", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    if (signal.aborted) return abort();
    signal.addEventListener("abort", abort, { once: true });
  });
}
async function readAnalysisStatus(jobId, signal) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await request("/result/" + encodeURIComponent(jobId), {}, signal);
    } catch (error) {
      const transient = error instanceof TypeError || error.name === "AbortError" ||
        [502, 503, 504].includes(error.status);
      if (signal.aborted || !transient || attempt === 2) throw error;
      status(t("Connection interrupted; retrying this analysis without uploading again...",
        "\u0627\u062a\u0635\u0627\u0644 \u0642\u0637\u0639 \u0634\u062f\u061b \u062a\u0644\u0627\u0634 \u0645\u062c\u062f\u062f \u0628\u062f\u0648\u0646 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0645\u062c\u062f\u062f..."));
      await pause(750 * (attempt + 1), signal);
    }
  }
}

async function uploadAndAnalyze(file) {
  if (analysisController) return;
  if (!/\.(csv|xlsx|xls)$/i.test(file.name)) {
    status(t("Choose a CSV or Excel file", "فایل CSV یا Excel انتخاب کنید"));
    return;
  }
  const budget = Number($("budget").value);
  if (
    !Number.isFinite(budget) ||
    budget <= 0 ||
    !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test($("shopId").value.trim())
  ) {
    status(
      t(
        "Enter a valid shop ID (1–64 letters, digits, _ or -) and a budget above zero",
        "شناسه فروشگاه و بودجه معتبر وارد کنید",
      ),
    );
    return;
  }
  const controller = new AbortController();
  analysisController = controller;
  $("loadingOverlay").hidden = false;
  $("uploadBtn").disabled = true;
  $("cancelAnalysis").focus();
  const form = new FormData();
  form.append("file", file);
  form.append("shop_id", $("shopId").value.trim());
  form.append("budget", String(budget));
  form.append("goal", $("goal").value);
  form.append("language", language);
  try {
    status(t("Uploading sales…", "بارگذاری فروش…"));
    const job = await request(
      "/analyze",
      { method: "POST", body: form },
      controller.signal,
    );
    if (!job.job_id) throw new Error("The server did not return a job ID.");
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      status(t("Analyzing sales…", "تحلیل فروش…"));
      const data = await readAnalysisStatus(job.job_id, controller.signal);
      if (data.status === "done") {
        const result = data.result || data;
        if (result.passed === false)
          throw new Error(
            t("Data quality check failed: ", "????? ????? ???? ??????: ") +
              String(
                result.stop_reason ||
                  t(
                    "Please review your sales file.",
                    "???? ???? ?? ????? ????.",
                  ),
              ),
          );
        report = result.report || result;
        inventory =
          result.current_inventory ||
          result.inventory ||
          data.current_inventory ||
          data.inventory ||
          {};
        page = 1;
        renderCurrentTab();
        status(
          t(
            "Analysis complete · ready to review",
            "تحلیل کامل شد · آماده بررسی",
          ),
        );
        addBotMessage(
          t(
            "Analysis is ready. Ask about stock, purchases, demand or profit.",
            "تحلیل آماده است. درباره موجودی، خرید، تقاضا یا سود بپرسید.",
          ),
        );
        return;
      }
      if (data.status === "error")
        throw new Error(String(data.error || "Analysis failed"));
      await pause(2000, controller.signal);
    }
    throw new Error(
      t(
        "Analysis timed out. Try a smaller file or check the server.",
        "زمان تحلیل تمام شد. فایل کوچک‌تر یا سرور را بررسی کنید.",
      ),
    );
  } catch (error) {
    status(
      controller.signal.aborted
        ? t(
            "Waiting cancelled. The server job may still finish.",
            "انتظار لغو شد؛ ممکن است پردازش سرور ادامه داشته باشد.",
          )
        : t("Analysis failed: ", "تحلیل ناموفق: ") + error.message,
    );
  } finally {
    analysisController = null;
    $("loadingOverlay").hidden = true;
    $("uploadBtn").disabled = false;
    $("fileInput").value = "";
    $("uploadBtn").focus();
  }
}
$("uploadBtn").onclick = () => $("fileInput").click();
$("fileInput").onchange = (e) => {
  if (e.target.files[0]) uploadAndAnalyze(e.target.files[0]);
};
$("cancelAnalysis").onclick = () => analysisController?.abort();
function addBotMessage(text) {
  addMessage(text, "message-bot");
}
function addMessage(text, kind) {
  const div = document.createElement("div");
  div.className = kind;
  div.textContent = String(text);
  $("llmMessages").append(div);
  $("llmMessages").scrollTop = $("llmMessages").scrollHeight;
}
function smartAnswer(question) {
  if (!report)
    return t(
      "Upload sales data first so I can answer using your shop analysis.",
      "ابتدا فایل فروش را بارگذاری کنید.",
    );
  const q = question.toLocaleLowerCase(),
    products = getProducts(),
    orders = getOrders().filter((o) => n(o.qty) > 0);
  const contains = (words) => words.some((w) => q.includes(w));
  const product = products.find((p) =>
    q.includes(String(p.product).toLocaleLowerCase()),
  );
  if (product) {
    const stock = Object.hasOwn(inventory, product.product)
      ? inventory[product.product]
      : null;
    return `${product.product}\n${t("Stock", "موجودی")}: ${num(stock)}\n${t("30-day demand", "تقاضای ۳۰ روز")}: ${num(product.forecast?.h30)}\n${t("Margin", "حاشیه سود")}: ${num(product.profit_margin, 1)}%\n${t("Risk", "ریسک")}: ${num(product.risk_score)}`;
  }
  if (contains(["order", "buy", "purchase", "reorder", "خرید", "سفارش"]))
    return orders.length
      ? orders
          .map((o) => `${o.product}: ${num(o.qty)} · ${o.reason || ""}`)
          .join("\n")
      : t(
          "No purchase recommendations in this analysis.",
          "پیشنهاد خریدی وجود ندارد.",
        );
  if (contains(["stock", "inventory", "موجودی", "انبار"])) {
    const entries = Object.entries(inventory);
    return entries.length
      ? entries
          .map(
            ([p, q]) =>
              `${p}: ${num(q)}${q != null && n(q) < 20 ? " · " + t("Review stock", "بررسی موجودی") : ""}`,
          )
          .join("\n")
      : t(
          "Inventory information is unavailable; missing stock is not zero.",
          "اطلاعات موجودی در دسترس نیست؛ مقدار نامشخص به معنی صفر نیست.",
        );
  }
  if (contains(["top", "best", "leader", "برتر", "بهترین"]))
    return (
      [...products]
        .sort((a, b) => n(b.total_revenue) - n(a.total_revenue))
        .slice(0, 5)
        .map(
          (p) =>
            `${p.product}: ${num(p.total_revenue)} ${t("Toman revenue", "تومان درآمد")}`,
        )
        .join("\n") || t("No products available.", "محصولی موجود نیست.")
    );
  if (contains(["risk", "ریسک"]))
    return (
      products
        .filter((p) => n(p.risk_score) > 70)
        .map((p) => `${p.product}: ${num(p.risk_score)}`)
        .join("\n") ||
      t(
        "No products have a risk score above 70.",
        "محصولی با امتیاز ریسک بالای ۷۰ نیست.",
      )
    );
  if (contains(["profit", "margin", "roi", "سود", "بازده"]))
    return `${t("Shop ROI", "بازده فروشگاه")}: ${num(report.shop_roi, 1)}%\n${t("Average product margin", "میانگین حاشیه سود")}: ${products.length ? num(products.reduce((s, p) => s + n(p.profit_margin), 0) / products.length, 1) : "—"}%`;
  if (contains(["forecast", "future", "demand", "تقاضا", "پیش‌بینی"]))
    return (
      products
        .filter((p) => p.forecast && !p.forecast.skipped)
        .map(
          (p) =>
            `${p.product}: ${num(p.forecast.h30)} · ${t("30-day demand", "تقاضای ۳۰ روز")}`,
        )
        .join("\n") || t("No forecast data available.", "پیش‌بینی موجود نیست.")
    );
  if (contains(["segment", "category", "دسته"]))
    return products
      .map((p) => `${p.product}: ${p.segment || "Individual"}`)
      .join("\n");
  if (contains(["basket", "together", "combo", "سبد", "همراه"]))
    return (
      getBasketRules()
        .map(
          (r) =>
            `${(r.antecedent || []).join(" + ")} → ${(r.consequent || []).join(" + ")} (${num(n(r.confidence) * 100)}%)`,
        )
        .join("\n") ||
      t(
        "Not enough transactions for basket rules.",
        "تراکنش کافی برای تحلیل سبد نیست.",
      )
    );
  if (contains(["why", "explain", "چرا"]))
    return (
      (report.priority_actions || [])
        .map((a) => `${a.title}: ${a.description}`)
        .join("\n") ||
      t(
        "No priority actions identified. Review product risk and stock details.",
        "اقدام فوری شناسایی نشده است. جزئیات ریسک و موجودی را بررسی کنید.",
      )
    );
  return t(
    "Ask about purchases, stock, top products, risk, profit, demand, segments, basket rules, or a product by name.",
    "درباره خرید، موجودی، محصولات برتر، ریسک، سود، تقاضا، دسته‌ها، سبد یا نام محصول بپرسید.",
  );
}
async function sendLlm(e) {
  e.preventDefault();
  const question = $("llmInput").value.trim();
  if (!question || $("llmSend").disabled) return;
  addMessage(question, "message-user");
  $("llmInput").value = "";
  $("llmInput").disabled = $("llmSend").disabled = true;
  try {
    if (llmMode === "real") {
      const forecasts = Object.fromEntries(
        getProducts()
          .filter((p) => p.forecast)
          .map((p) => [p.product, p.forecast]),
      );
      const data = await request("/llm/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          report_summary: report,
          inventory,
          forecasts,
          talk: talkMode,
          language,
        }),
      });
      addBotMessage(
        data.answer || t("No answer returned.", "پاسخی دریافت نشد."),
      );
    } else addBotMessage(smartAnswer(question));
  } catch {
    addBotMessage(
      t(
        "The language model is unavailable. Here is the local advisor response:",
        "مدل زبانی در دسترس نیست. پاسخ مشاور محلی:",
      ),
    );
    addBotMessage(smartAnswer(question));
  } finally {
    $("llmInput").disabled = $("llmSend").disabled = false;
    $("llmInput").focus();
  }
}
function toggleChat(open) {
  $("llmPanel").hidden = !open;
  $("llmToggle").hidden = open;
  $("llmToggle").setAttribute("aria-expanded", String(open));
  (open ? $("llmInput") : $("llmToggle")).focus();
}
$("llmToggle").onclick = () => toggleChat(true);
$("closeLlm").onclick = () => toggleChat(false);
$("chatForm").onsubmit = sendLlm;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (analysisController) analysisController.abort();
    else if (!$("llmPanel").hidden) toggleChat(false);
  }
});
addBotMessage(
  "Welcome to SaleYar. Ask about your shop after uploading sales data.",
);
$("llmMessages").lastElementChild.id = "advisorWelcome";
renderNav();
renderCurrentTab();
