# config.py — One Size Fits All Shops (Tiny to Large)

from dotenv import load_dotenv
import os

load_dotenv()

# ============================================================================
# API & SERVER
# ============================================================================
API_KEY = os.getenv("API_KEY", "kamal")
DEFAULT_LANGUAGE = "en"
MAX_FILE_SIZE_MB = 50
MAX_CONCURRENT_JOBS = 2
REPORT_RETENTION_DAYS = 90

# ============================================================================
# FINANCIAL BENCHMARKS
# ============================================================================
BANK_DEPOSIT_RATE_ANNUAL = 23.0
GOLD_ANNUAL_RETURN = 35.0
RETAIL_AVG_MARGIN = 18.0
RETAIL_AVG_TURNOVER = 8.0

# ============================================================================
# PIPELINE THRESHOLDS (Works for ANY shop size)
# ============================================================================
MIN_SALES_RICH = 8              # 8+ sales = rich history (AutoTheta)
MIN_SALES_MEDIUM = 2            # 2+ sales = medium (AutoETS)
MIN_BASKET_ROWS = 20            # 20 transactions minimum for basket
MIN_PRODUCTS = 8                # 8 products minimum for clustering
MIN_CUSTOMERS = 2               # 2 customers minimum for segmentation
FORECAST_HORIZON = 60           # 60 days forecast (good for monthly data)

# ============================================================================
# STAGE 1: CLEANER (Adaptive)
# ============================================================================
ALLOW_RETURNS = True
ALLOW_DAMAGED = True
ALLOW_PROMOTIONS = True
MAX_REASONABLE_LOSS = 50
MIN_REASONABLE_QTY = -100
MAX_REASONABLE_QTY = 500

SMALL_SHOP_ROWS = 50            # <50 rows = small shop
QUALITY_PASS_SMALL = 30         # Easier pass for small shops
QUALITY_PASS_NORMAL = 40
LARGE_FILE_CLEANER = 20000      # Skip fuzzy matching above 20k rows

# ============================================================================
# STAGE 2: KPIs & UNIFIED SCORE
# ============================================================================
UNIFIED_SCORE_WEIGHTS = {
    "profit_margin": 0.25,
    "sales_velocity": 0.25,
    "liquidity_rate": 0.20,
    "inverse_risk": 0.15,
    "customer_demand": 0.15
}
OUTLIER_PERCENTILE_CLIP = (1, 99)
CATEGORY_FALLBACK_ENABLED = True

# ============================================================================
# STAGE 3: FORECAST (Works for ANY data volume)
# ============================================================================
MIN_DAYS_FOR_FORECAST = 3           # 3 days minimum (very small shops)
SEASON_LENGTH = None
FORECAST_BATCH_SIZE = 100           # Batch size for speed
ENABLE_TREND_ADJUSTMENT = True
MIN_TREND_THRESHOLD = 0.10          # 10% trend needed to adjust
TREND_WEIGHT = 0.3                  # Low trend influence

FORECAST_SPARSE_USE_CATEGORY = True
FORECAST_CONFIDENCE_MAPE_HIGH = 40   # 40% error = High confidence
FORECAST_CONFIDENCE_MAPE_LOW = 70    # 70% error = Low confidence
LOW_CONFIDENCE_MULTIPLIER = 0.5      # 50% of forecast for low confidence

# ============================================================================
# STAGE 4: SEGMENTS (Adaptive)
# ============================================================================
MIN_PRODUCTS_CLUSTER = 8             # Cluster if >=8 products
OUTLIER_THRESHOLD = 2.0
OUTLIER_THRESHOLD_SMALL = 2.5
RISKY_VOLATILITY_THRESHOLD = 100

STAR_MARGIN_MIN = 12                 # 12% margin = Star (was 15)
STAR_LIQUIDITY_MIN = 35              # 35% liquidity (was 40)

SEASONAL_CORRELATION_THRESHOLD = 0.2

# ============================================================================
# STAGE 5: BASKET ANALYSIS (Adaptive)
# ============================================================================
CRITICAL_PAIR_CONFIDENCE = 0.65      # 65% confidence = critical (was 70)
BASKET_TINY_FALLBACK = True
BASKET_MAX_PRODUCTS = 200
BASKET_SAMPLE_SIZE = 2000

def get_min_support(n_transactions: int) -> float:
    if n_transactions < 50:
        return 0.20          # Very small shop
    elif n_transactions < 200:
        return 0.12          # Small shop
    elif n_transactions < 1000:
        return 0.08          # Medium shop
    else:
        return 0.04          # Large shop

# ============================================================================
# STAGE 6: RISK SCORING
# ============================================================================
RISK_BASE = 50.0
RISK_MARGIN_WEIGHT = 0.5
RISK_LIQUIDITY_WEIGHT = 0.3
RISK_VOLATILITY_WEIGHT = -0.2
RISK_IDLE_WEIGHT = -0.05
RISK_CONVERSION_WEIGHT = 0.2

RISK_MARGIN_MAX = 25.0
RISK_LIQUIDITY_MAX = 15.0
RISK_VOLATILITY_MIN = -15.0
RISK_IDLE_MIN = -20.0
RISK_CONVERSION_MAX = 10.0

HYBRID_MIN_CONFIDENCE = 0.3
HYBRID_MAX_CONFIDENCE = 0.7

RISK_SMALL_SHOP_MAX_PRODUCTS = 20
RISK_SMALL_SHOP_MODEL_WEIGHT = 0.2

# ============================================================================
# STAGE 7: OPTIMIZER (Safe for ALL shops)
# ============================================================================
MAX_ORDER_UNITS_PER_PRODUCT = 200     # Safe max for any shop
MIN_SHELF_QUANTITY = 1
MIN_PRODUCTS_IN_ORDER = 3             # Minimum 3 products per order
MAX_COVERAGE_DAYS = 45                # 45 days coverage
MIN_UNIT_COST_FOR_LARGE_ORDER = 1000

MAX_SINGLE_PRODUCT_SHARE = 0.35       # Max 35% of budget on one product
SAFETY_STOCK_DAYS = 7
STAR_COVERAGE_DAYS = 30
RELIABLE_COVERAGE_DAYS = 21
SEASONAL_COVERAGE_DAYS = 14

OPTIMIZER_GREEDY_FALLBACK = True
OPTIMIZER_MAX_PRODUCTS_FOR_SCIP = 500

# ============================================================================
# STAGE 8: CUSTOMERS (Works for ANY customer count)
# ============================================================================
CUSTOMER_SINGLE_HANDLING = True
RFM_LOG_TRANSFORM = True
CUSTOMER_CLUSTER_FALLBACK = "percentile"

# ============================================================================
# STAGE 9: PRIORITY ACTIONS (Safe defaults)
# ============================================================================
PRIORITY_REVENUE_DROP_THRESHOLD = 20   # 20% drop triggers alert
PRIORITY_DEADSTOCK_DAYS = 60           # 60 days idle = deadstock
PRIORITY_HIGH_RISK_THRESHOLD = 70

# ============================================================================
# MODELS & PATHS
# ============================================================================
LGBM_MODEL_PATH = "models/lgbm_risk.pkl"
SHOPS_DIR = "models/shops"
SAVE_REPORTS_TO_DISK = False

# ============================================================================
# LLM (OPTIONAL)
# ============================================================================
LLM_ENABLED = os.getenv("LLM_ENABLED", "yes").lower() in ("1", "true", "yes")
LLM_ENDPOINT_URL = os.getenv("LLM_ENDPOINT_URL", "")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "15"))