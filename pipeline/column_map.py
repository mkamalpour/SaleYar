"""
column_map.py

Maps every known Holoo column header variant — Persian, English, or mixed —
to the internal standard schema used by all pipeline stages.

After testing on a real Holoo CSV export, add any unrecognised column names here.
The fuzzy matcher in stage1_cleaner.py catches close variants automatically,
but exact matches listed here are faster and safer.

SUPPORTED COLUMNS (your actual data format):
- invoice_id, date, product, qty, buy_price, sell_price
- customer_id, customer_name, customer_segment, product_category
- transaction_type (CRITICAL for inventory tracking)
- discount, tax, unit, warehouse
"""

import pandas as pd

# ============================================================================
# INTERNAL SCHEMA
# ============================================================================

REQUIRED_FIELDS = [
    "invoice_id",
    "date",
    "product",
    "qty",
    "buy_price",
    "sell_price",
    "transaction_type" # ← CRITICAL for inventory tracking
]

OPTIONAL_FIELDS = [
    "customer_id",
    "customer_name",
    "customer_segment",
    "product_category",
    "category",
    "unit",
    "discount",
    "tax",
    "warehouse",     
    "time",
    "comment",
]

# ============================================================================
# COLUMN MAPPING (source → internal)
# ============================================================================

COLUMN_MAP = {
    # ═══════════════════════════════════════════════════════════════════════
    # invoice_id — شناسه فاکتور
    # ═══════════════════════════════════════════════════════════════════════
    "invoice_id":           "invoice_id",
    "invoice id":           "invoice_id",
    "invoice no":           "invoice_id",
    "invoice number":       "invoice_id",
    "inv id":               "invoice_id",
    "inv no":               "invoice_id",
    "inv_no":               "invoice_id",
    "inv_num":              "invoice_id",
    "facture_id":           "invoice_id",
    "شماره فاکتور":          "invoice_id",
    "شماره":                 "invoice_id",
    "فاکتور":                "invoice_id",
    "شماره سند":             "invoice_id",
    "شماره فاکتور فروش":     "invoice_id",
    "کد فاکتور":             "invoice_id",
    "شماره فاکتور خرید":     "invoice_id",

    # ═══════════════════════════════════════════════════════════════════════
    # date — تاریخ
    # ═══════════════════════════════════════════════════════════════════════
    "date":                 "date",
    "invoice date":         "date",
    "sale date":            "date",
    "sales date":           "date",
    "transaction date":     "date",
    "trx_date":             "date",
    "inv_date":             "date",
    "تاریخ":                 "date",
    "تاریخ فاکتور":          "date",
    "تاریخ فروش":            "date",
    "تاریخ ثبت":             "date",
    "تاریخ سند":             "date",
    "تاریخ معامله":          "date",
    "تاریخ خرید":            "date",

    # ═══════════════════════════════════════════════════════════════════════
    # time — زمان (optional)
    # ═══════════════════════════════════════════════════════════════════════
    "time":                 "time",
    "ساعت":                  "time",
    "زمان":                  "time",

    # ═══════════════════════════════════════════════════════════════════════
    # product — نام کالا / محصول
    # ═══════════════════════════════════════════════════════════════════════
    "product":              "product",
    "product name":         "product",
    "product_name":         "product",
    "item":                 "product",
    "item name":            "product",
    "item_name":            "product",
    "description":          "product",
    "goods":                "product",
    "commodity":            "product",
    "article":              "product",
    "کالا":                  "product",
    "نام کالا":              "product",
    "نام محصول":             "product",
    "شرح کالا":              "product",
    "شرح":                   "product",
    "محصول":                 "product",
    "نام":                   "product",
    "عنوان کالا":            "product",
    "کد کالا":               "product",

    # ═══════════════════════════════════════════════════════════════════════
    # qty — تعداد / مقدار
    # ═══════════════════════════════════════════════════════════════════════
    "qty":                  "qty",
    "quantity":             "qty",
    "amount":               "qty",
    "count":                "qty",
    "units":                "qty",
    "unit_qty":             "qty",
    "تعداد":                 "qty",
    "مقدار":                 "qty",
    "تعداد فروش":            "qty",
    "تعداد کالا":            "qty",
    "عدد":                   "qty",
    "تعداد خرید":            "qty",

    # ═══════════════════════════════════════════════════════════════════════
    # buy_price — قیمت خرید / بهای تمام شده
    # ═══════════════════════════════════════════════════════════════════════
    "buy_price":            "buy_price",
    "buy price":            "buy_price",
    "buyprice":             "buy_price",
    "purchase price":       "buy_price",
    "purchase_price":       "buy_price",
    "cost":                 "buy_price",
    "unit cost":            "buy_price",
    "unit_cost":            "buy_price",
    "cost price":           "buy_price",
    "costprice":            "buy_price",
    "قیمت خرید":             "buy_price",
    "بهای تمام شده":         "buy_price",
    "قیمت تمام شده":         "buy_price",
    "قیمت خرید واحد":        "buy_price",
    "خرید":                  "buy_price",
    "بها":                   "buy_price",
    "هزینه":                 "buy_price",
    "قیمت تمام شده کالا":    "buy_price",

    # ═══════════════════════════════════════════════════════════════════════
    # sell_price — قیمت فروش
    # ═══════════════════════════════════════════════════════════════════════
    "sell_price":           "sell_price",
    "sell price":           "sell_price",
    "sellprice":            "sell_price",
    "sale price":           "sell_price",
    "saleprice":            "sell_price",
    "selling price":        "sell_price",
    "selling_price":        "sell_price",
    "unit price":           "sell_price",
    "unit_price":           "sell_price",
    "price":                "sell_price",
    "قیمت فروش":             "sell_price",
    "قیمت":                  "sell_price",
    "قیمت واحد":             "sell_price",
    "قیمت فروش واحد":        "sell_price",
    "فروش":                  "sell_price",
    "مبلغ":                  "sell_price",
    "قیمت نهایی":            "sell_price",

    # ═══════════════════════════════════════════════════════════════════════
    # customer_id — کد مشتری
    # ═══════════════════════════════════════════════════════════════════════
    "customer_id":          "customer_id",
    "customer id":          "customer_id",
    "customerid":           "customer_id",
    "client id":            "customer_id",
    "client_id":            "customer_id",
    "clientid":             "customer_id",
    "cust_id":              "customer_id",
    "کد مشتری":              "customer_id",
    "کد خریدار":             "customer_id",
    "کد طرف حساب":           "customer_id",
    "شناسه مشتری":           "customer_id",
    "کد مشتری":              "customer_id",
    "شماره مشتری":           "customer_id",

    # ═══════════════════════════════════════════════════════════════════════
    # customer_name — نام مشتری
    # ═══════════════════════════════════════════════════════════════════════
    "customer_name":        "customer_name",
    "customer name":        "customer_name",
    "customername":         "customer_name",
    "client":               "customer_name",
    "client name":          "customer_name",
    "client_name":          "customer_name",
    "نام مشتری":             "customer_name",
    "خریدار":                "customer_name",
    "نام طرف حساب":          "customer_name",
    "نام خریدار":            "customer_name",
    "نام":                   "customer_name",

    # ═══════════════════════════════════════════════════════════════════════
    # customer_segment — بخش مشتری / گروه مشتری
    # ═══════════════════════════════════════════════════════════════════════
    "customer_segment":     "customer_segment",
    "customer segment":     "customer_segment",
    "cust_segment":         "customer_segment",
    "segment":              "customer_segment",
    "بخش مشتری":             "customer_segment",
    "بخش":                   "customer_segment",
    "گروه مشتری":            "customer_segment",
    "نوع مشتری":             "customer_segment",
    "دسته مشتری":            "customer_segment",
    "بخش بندی":              "customer_segment",
    "رده مشتری":             "customer_segment",

    # ═══════════════════════════════════════════════════════════════════════
    # product_category — دسته‌بندی کالا
    # ═══════════════════════════════════════════════════════════════════════
    "product_category":     "product_category",
    "product category":     "product_category",
    "productcategory":      "product_category",
    "category":             "product_category",
    "cat":                  "product_category",
    "prod_cat":             "product_category",
    "دسته‌بندی":             "product_category",
    "دسته بندی":             "product_category",
    "دسته":                  "product_category",
    "گروه کالا":             "product_category",
    "دسته کالا":             "product_category",
    "رده":                   "product_category",
    "زیرگروه":               "product_category",
    "دسته محصول":            "product_category",
    "گروه محصول":            "product_category",

    # ═══════════════════════════════════════════════════════════════════════
    # transaction_type — نوع تراکنش (CRITICAL for inventory tracking)
    # ═══════════════════════════════════════════════════════════════════════
    "transaction_type":     "transaction_type",
    "transaction type":     "transaction_type",
    "trans_type":           "transaction_type",
    "trx_type":             "transaction_type",
    "نوع تراکنش":            "transaction_type",
    "نوع عملیات":            "transaction_type",
    "نوع":                   "transaction_type",
    "نوع تراکنش فروش":       "transaction_type",
    "نوع سند":               "transaction_type",
    "نوع فاکتور":            "transaction_type",

    # ═══════════════════════════════════════════════════════════════════════
    # discount — تخفیف
    # ═══════════════════════════════════════════════════════════════════════
    "discount":             "discount",
    "تخفیف":                 "discount",
    "تخفیف درصدی":           "discount",
    "مبلغ تخفیف":            "discount",

    # ═══════════════════════════════════════════════════════════════════════
    # tax — مالیات
    # ═══════════════════════════════════════════════════════════════════════
    "tax":                  "tax",
    "vat":                  "tax",
    "مالیات":                "tax",
    "مالیات بر ارزش افزوده": "tax",

    # ═══════════════════════════════════════════════════════════════════════
    # unit — واحد
    # ═══════════════════════════════════════════════════════════════════════
    "unit":                 "unit",
    "uom":                  "unit",
    "واحد":                  "unit",
    "واحد اندازه گیری":       "unit",
    "واحد کالا":             "unit",

    # ═══════════════════════════════════════════════════════════════════════
    # warehouse — انبار
    # ═══════════════════════════════════════════════════════════════════════
    "warehouse":            "warehouse",
    "انبار":                 "warehouse",
    "نام انبار":             "warehouse",
    "کد انبار":              "warehouse",

    # ═══════════════════════════════════════════════════════════════════════
    # comment — توضیحات
    # ═══════════════════════════════════════════════════════════════════════
    "comment":              "comment",
    "توضیحات":               "comment",
    "شرح":                   "comment",
    "یادداشت":               "comment",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def map_column(col_name: str) -> str:
    """
    Map a column name to internal schema.
    
    Args:
        col_name: Original column name from CSV/Excel
        
    Returns:
        Mapped internal field name, or original name if not found
    """
    if not col_name or pd.isna(col_name):
        return col_name
    
    # Clean and lowercase
    cleaned = str(col_name).strip().lower()
    
    # Check exact match in map
    if cleaned in COLUMN_MAP:
        return COLUMN_MAP[cleaned]
    
    # Check if any key in map is contained in the column name
    for key, value in COLUMN_MAP.items():
        if key in cleaned:
            return value
    
    # Return original if no match
    return col_name


def map_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply column mapping to entire DataFrame.
    
    Args:
        df: Input DataFrame with original column names
        
    Returns:
        DataFrame with mapped column names
    """
    mapping = {col: map_column(col) for col in df.columns}
    return df.rename(columns=mapping)


def get_required_columns() -> list:
    """Return list of required column names."""
    return REQUIRED_FIELDS.copy()


def get_optional_columns() -> list:
    """Return list of optional column names."""
    return OPTIONAL_FIELDS.copy()


def get_all_expected_columns() -> list:
    """Return all columns the pipeline understands."""
    return REQUIRED_FIELDS + OPTIONAL_FIELDS


def validate_columns(df: pd.DataFrame) -> tuple:
    """
    Validate that DataFrame has required columns.
    
    Returns:
        (has_required: bool, missing: list, found: list)
    """
    mapped_df = map_dataframe_columns(df)
    found = [col for col in REQUIRED_FIELDS if col in mapped_df.columns]
    missing = [col for col in REQUIRED_FIELDS if col not in mapped_df.columns]
    return len(missing) == 0, missing, found


# ============================================================================
# TRANSACTION TYPE CONSTANTS
# ============================================================================

TRANSACTION_TYPES = {
    "sale": "sale",                    # Normal sale (decreases inventory)
    "return_sale": "return_sale",      # Customer return (increases inventory)
    "purchase": "purchase",            # Purchase from supplier (increases inventory)
    "return_purchase": "return_purchase",  # Return to supplier (decreases inventory)
    "damaged": "damaged",              # Damaged goods (decreases inventory)
    "adjustment": "adjustment",        # Manual inventory adjustment
    "gift": "gift",                    # Free sample/gift (decreases inventory)
}

# Mapping for Persian values
TRANSACTION_TYPES_FA = {
    "فروش": "sale",
    "برگشت از فروش": "return_sale",
    "خرید": "purchase",
    "برگشت از خرید": "return_purchase",
    "آسیب دیده": "damaged",
    "تعدیل": "adjustment",
    "هدیه": "gift",
}


def normalize_transaction_type(trans_type: str) -> str:
    """
    Normalize transaction type to internal standard.
    Handles both English and Persian values.
    """
    if not trans_type or pd.isna(trans_type):
        return "sale"
    
    trans_str = str(trans_type).strip().lower()
    
    # Check English mapping
    if trans_str in TRANSACTION_TYPES:
        return TRANSACTION_TYPES[trans_str]
    
    # Check Persian mapping
    if trans_str in TRANSACTION_TYPES_FA:
        return TRANSACTION_TYPES_FA[trans_str]
    
    # Default to sale
    return "sale"


# ============================================================================
# TEST/EXAMPLE
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("COLUMN MAP TEST")
    print("=" * 60)
    
    # Test Persian column names
    test_columns = [
        "شماره فاکتور",
        "تاریخ",
        "نام کالا",
        "تعداد",
        "قیمت خرید",
        "قیمت فروش",
        "کد مشتری",
        "بخش مشتری",
        "دسته‌بندی",
        "نوع تراکنش",
    ]
    
    print("\nPersian → Internal mapping:")
    for col in test_columns:
        mapped = map_column(col)
        print(f"  {col:15} → {mapped}")
    
    # Test transaction type normalization
    print("\nTransaction type normalization:")
    test_types = ["sale", "فروش", "return_sale", "برگشت از فروش", "purchase", "خرید"]
    for t in test_types:
        normalized = normalize_transaction_type(t)
        print(f"  {t:20} → {normalized}")
    
    print("\n" + "=" * 60)
    print("✅ COLUMN MAP READY")
    print("=" * 60)