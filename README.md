# SaleYar — Shop Advisor

**Offline business intelligence for Iranian shops.**

SaleYar reads Holoo invoice exports and tells shop owners what to buy, what to avoid, and why — in plain Persian or English. No cloud. No internet required after install. Your data never leaves your computer.


          ⚡ Offline Business Intelligence ⚡          
                  MADE BY KamalAi                     


## ✨ What It Does

- ✅ **Data quality check** – Tells you exactly what to fix before analysis  
- 📊 **Product KPIs** – Profit margin, sales speed, price changes, best selling season  
- 🔮 **Demand forecast** – 30, 60, 90 days ahead with confidence bands  
- 🏷️ **Smart segments** – Star / Reliable / Seasonal / Deadweight / Risky / Outlier  
- 🛒 **Basket analysis** – Which products are bought together (e.g., rice + oil)  
- ⚠️ **Risk score** – 0–100 per product, plain English explanation  
- 💰 **ROI comparison** – Your shop vs bank deposit (23%) vs gold return (35%)  
- 👥 **Customer groups** – Champions, Loyal, At‑Risk, Lost  
- 📦 **Shopping list** – Exact whole quantities for your budget  
- 🎯 **Top 3 actions** – The most important things to do right now  
- ❤️ **Health score** – 0–100 overall shop health  

No jargon. Every number is explained. If a stage is skipped (not enough data), it tells you why.

---

## 🏠 Owner Dashboard – HTML (recommended)

When you run `python run.py` and choose option 1, you get a **pure HTML/CSS/JS dashboard** that runs in your browser and connects to the SaleYar API.

**Features:**
- **9 tabs:** Overview, Purchase Orders, Forecast, Products, Segments, Basket, Inventory, Customers & ROI, Settings.
- **Real‑time polling** – Upload file → analysis runs in background, dashboard updates automatically.
- **Global search** – Filter products, inventory, orders, or forecast by name.
- **Budget, goal, language, shop ID** controls in the top bar.
- **Purchase Orders tab:** All products appear. Each shows current stock, recommended quantity (max 500 units), unit cost, total cost, and plain‑language “why”. Copy list / export CSV.
- **Products tab:** Ranked list (1,2,3…) with unified score, segment, revenue (M), profit (M), margin %, risk score (🟢🟡🔴), stock, last sale, risk explanation. Searchable.
- **Inventory tab:** Stock levels, days of coverage, status (OUT/LOW/OK/OVERSTOCK), and actions (ORDER NOW, ORDER THIS WEEK, RUN SALE).
- **LLM Advisor** – floating robot panel:
  - **Keyword mode** – fast, offline, rule‑based.
  - **Real LLM mode** – connects to a local LLM (LM Studio or Ollama).
  - **Talk Mode toggle** (in Settings):
    - **ON** → ultra‑short conversational answers (max 10 words), uses micro‑summary (health %, revenue/profit in millions, out‑of‑stock count, top seller). Greetings/thanks get no numbers. “How to find X?” → tells exact tab name.
    - **OFF** → gives 4 bullet points (like Gradio), uses full summary.
  - **Markdown support** – bot messages render **bold**, *italic*, bullet lists using `marked.js`.
  - Send button disabled while waiting for response.
- **Settings tab:** API Base URL, API Key, AI Advisor Mode, Talk Mode. Settings saved in `localStorage`.

Launch with `python run.py --mode owner` (defaults to HTML).

---

## 🔧 Developer UI – Gradio

For advanced users and debugging, run `python run.py --mode developer` (option 2). This gives 11 tabs with full data visibility:
- Health & Quality (charts, column stats, preview)
- Product Rankings (search + rank column)
- Forecast, Segments, Basket Rules, Purchase Order
- ROI & Customers, Inventory, Priority Actions
- LLM Advisor (always returns 4 bullet points – no Talk Mode)
- JSON Report

---

## ⌨️ Terminal Mode

Run `python run.py --mode terminal` (option 3). Interactive command line with rich tables. No browser needed.

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
conda create -n saleyar python=3.10 -y
conda activate saleyar

conda install pandas numpy scikit-learn lightgbm openpyxl plotly -c conda-forge
pip install statsforecast mlxtend ortools fastapi uvicorn gradio jdatetime persiantools rapidfuzz python-dotenv joblib
```

### 2. Train the risk model (one time)

```bash
python models/train.py
```

### 3. Run the application

```bash
python run.py
```

Then choose:

- `1` – **Owner Dashboard (HTML)** – recommended for shop owners  
- `2` – **Developer UI (Gradio)** – for debugging  
- `3` – **Terminal mode**  
- `4` – **Generate sample data**  

Or run directly:

```bash
python run.py --mode owner
python run.py --mode developer
python run.py --mode terminal
```

### 4. Start the API server (optional)

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/docs` for interactive API documentation.

---

## 📂 What You Need

- A **CSV or Excel file** exported from Holoo accounting software  
- Columns should contain: invoice number, date, product name, quantity, buy price, sell price  
- Persian or English column names – the system auto‑detects them  

---

## ⚙️ How It Works – 9‑Stage Pipeline

| Stage | Name | What it does |
|-------|------|---------------|
| 1 | Cleaner | Reads file, validates data, assigns quality score. Stops if <40. |
| 2 | KPIs | Calculates profit margin, liquidity, volatility, daily sales, data sufficiency. |
| 3 | Forecast | Predicts 30/60/90‑day sales using AutoTheta, AutoETS, or SeasonalNaive. |
| 4 | Segments | Groups products into Star, Reliable, Seasonal, Deadweight, Risky, Outlier. |
| 5 | Basket | Mines frequent itemsets with FP‑Growth; finds critical pairs (≥70% confidence). |
| 6 | Risk | Hybrid rule‑based + LightGBM risk score (0‑100) and shop ROI vs benchmarks. |
| 7 | Optimizer | Integer programming (OR‑Tools) – creates exact shopping list for your budget. |
| 8 | Customers | RFM analysis (MiniBatchKMeans) – segments customers by behaviour. |
| 9 | Priority | Synthesises all stages into the top 3 actions for the shop owner. |

If there isn’t enough data for a stage, it skips it and explains why – never crashes.

---

## 📡 API Endpoints (when server is running)

All endpoints require `X-API-Key` header (default key: `kamal` – change it in `.env`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/analyze` | Upload file, run full pipeline (async, returns job_id) |
| GET | `/result/{job_id}` | Poll for completion |
| POST | `/optimize` | Budget optimizer only (<2s) |
| POST | `/basket` | Basket analysis only |
| POST | `/risk` | Risk scoring only |
| POST | `/llm/ask` | LLM advisor – accepts `question`, `report_summary`, `inventory`, `forecasts`, `language`, `talk` (bool) |
| GET | `/report/{shop_id}` | Latest saved report (JSON) |
| GET | `/health/{shop_id}` | Health score only |
| GET | `/healthcheck` | Server status, loaded models, uptime |

---

## 🧪 Testing with Sample Data

Generate realistic sample data with:

```bash
python data/generate_data.py --invoices 15000 --customers 500 --seed 42
```

This creates `data/sample_en.csv` and `data/sample_fa.csv`. You can upload them directly to test the pipeline.

---

## 📦 Project Structure (Simplified)

```
saleyar/
├── pipeline/          # 9 stages (stage1_cleaner.py ... stage9_priority.py)
├── models/            # LightGBM model + per‑shop caches
├── ui/                # HTML dashboard, Gradio developer UI, terminal
├── api/               # FastAPI server
├── output/            # Report generator
├── llm/               # LLM advisor (talk modes, micro‑summary, tab guide)
├── data/              # Sample data generator
├── run.py             # Main launcher
├── config.py          # All thresholds & financial rates
```

---

## 📄 License

MIT – use freely, modify, and redistribute.

---

## 👤 Author

**kamal** – built for Iranian shop owners who want simple, offline analytics.

---

## ⭐ Support

If you find SaleYar useful, please ⭐ the repository.  
For issues or suggestions, open a GitHub issue.

**SaleYar – Your offline shop advisor. No cloud. No fees. No nonsense.**
