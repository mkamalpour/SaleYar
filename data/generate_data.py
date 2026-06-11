#!/usr/bin/env python3
"""
generate_data.py — DELIBERATE ARCHETYPE DATA GENERATOR FOR SALEYAR

- 45 products, each with a fixed role (Star, Reliable, Seasonal, Deadweight, etc.)
- Minimal dead stock (2 products only)
- Realistic restocking (based on demand)
- Product‑segment affinity (premium → VIP/Loyal)
- Strong basket rules (hand‑coded)
- Monthly promotions
- Perfect stock tracking with 4 transaction types

Run:
    python data/generate_data.py --invoices 20000 --customers 600 --seed 42
"""

import os
import random
import sys
import io
import argparse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def clean_old_files(data_dir="data"):
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        return
    for f in ["sample_en.csv", "sample_fa.csv", "sample_stock.csv"]:
        fp = os.path.join(data_dir, f)
        if os.path.exists(fp):
            os.remove(fp)
            print(f"[DELETED] {fp}")
    print("[OK] Cleaned old files\n")

# ============================================================================
# PRODUCT ARCHETYPES (deliberate, non‑random)
# ============================================================================
# Each product defines: name, category, buy_price, margin, seasonal pattern,
# trend, turnover, volatility, return_prone, affinity_segment, basket_group
# We'll build a list of 45 products explicitly (using templates for clarity).

PRODUCT_TEMPLATES = [
    # ----- STARS (high margin, high turnover) -----
    {"name": "Premium Basmati Rice", "category": "Staple", "buy_price": 450000, "margin": 0.28,
     "seasonal": "nowruz", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "rice"},
    {"name": "Organic Chicken", "category": "Meat", "buy_price": 320000, "margin": 0.20,
     "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "meat"},
    {"name": "Fresh Milk 1L", "category": "Dairy", "buy_price": 65000, "margin": 0.18,
     "seasonal": "none", "trend": "stable", "turnover": "ultra_fast", "volatility": "low", "return_prone": True, "affinity": "all", "basket_group": "dairy"},
    
    # ----- RELIABLE (medium margin, steady) -----
    {"name": "Cooking Oil", "category": "Staple", "buy_price": 380000, "margin": 0.15,
     "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "oil"},
    {"name": "Tomato Paste", "category": "Canned", "buy_price": 55000, "margin": 0.22,
     "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "canned"},
    {"name": "Yogurt", "category": "Dairy", "buy_price": 120000, "margin": 0.16,
     "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": True, "affinity": "all", "basket_group": "dairy"},
    
    # ----- SEASONAL (high margin, only peak months) -----
    {"name": "Fresh Saffron", "category": "Spice", "buy_price": 2800000, "margin": 0.65,
     "seasonal": "nowruz+yalda", "trend": "spike", "turnover": "seasonal", "volatility": "high", "return_prone": False, "affinity": "premium", "basket_group": "premium"},
    {"name": "Pistachios", "category": "Premium", "buy_price": 850000, "margin": 0.55,
     "seasonal": "yalda", "trend": "spike", "turnover": "seasonal", "volatility": "medium", "return_prone": False, "affinity": "premium", "basket_group": "premium"},
    {"name": "Summer Soft Drink", "category": "Beverage", "buy_price": 85000, "margin": 0.40,
     "seasonal": "summer", "trend": "spike", "turnover": "seasonal", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "drink"},
    
    # ----- DEADWEIGHT (low margin, low turnover) -----
    {"name": "Pickles (Jar)", "category": "Canned", "buy_price": 65000, "margin": 0.12,
     "seasonal": "none", "trend": "declining", "turnover": "slow", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "canned"},
    {"name": "Canned Tuna (Economy)", "category": "Canned", "buy_price": 180000, "margin": 0.10,
     "seasonal": "none", "trend": "declining", "turnover": "slow", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "canned"},
    
    # ----- RISKY (high volatility, erratic demand) -----
    {"name": "Luxury Dates", "category": "Premium", "buy_price": 450000, "margin": 0.45,
     "seasonal": "ramadan", "trend": "erratic", "turnover": "sporadic", "volatility": "high", "return_prone": False, "affinity": "premium", "basket_group": "premium"},
    {"name": "Imported Coffee", "category": "Beverage", "buy_price": 520000, "margin": 0.50,
     "seasonal": "none", "trend": "erratic", "turnover": "sporadic", "volatility": "very_high", "return_prone": False, "affinity": "premium", "basket_group": "drink"},
    
    # ----- OUTLIER (unique behavior) -----
    {"name": "Loss Leader Rice", "category": "Staple", "buy_price": 500000, "margin": -0.05,
     "seasonal": "none", "trend": "stable", "turnover": "ultra_fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "rice"},
    {"name": "Zero Margin Sugar", "category": "Staple", "buy_price": 250000, "margin": 0.00,
     "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "sugar"},
    
    # ----- DEAD STOCK (2 products only, discontinued after 1.5 years) -----
    {"name": "Discontinued Jam", "category": "Snack", "buy_price": 95000, "margin": 0.25,
     "seasonal": "none", "trend": "declining", "turnover": "dead", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "snack", "is_dead": True},
    {"name": "Old Cereal Brand", "category": "Snack", "buy_price": 120000, "margin": 0.18,
     "seasonal": "none", "trend": "declining", "turnover": "dead", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "snack", "is_dead": True},
    
    # ----- ADDITIONAL PRODUCTS TO REACH 45 (variations) -----
    {"name": "Whole Wheat Pasta", "category": "Staple", "buy_price": 180000, "margin": 0.22, "seasonal": "none", "trend": "growing", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "pasta"},
    {"name": "Organic Eggs", "category": "Dairy", "buy_price": 120000, "margin": 0.19, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": True, "affinity": "all", "basket_group": "eggs"},
    {"name": "Butter (Premium)", "category": "Dairy", "buy_price": 380000, "margin": 0.30, "seasonal": "none", "trend": "stable", "turnover": "medium", "volatility": "low", "return_prone": True, "affinity": "premium", "basket_group": "dairy"},
    {"name": "Honey (Natural)", "category": "Spice", "buy_price": 320000, "margin": 0.45, "seasonal": "nowruz", "trend": "stable", "turnover": "slow", "volatility": "low", "return_prone": False, "affinity": "premium", "basket_group": "sweet"},
    {"name": "Coffee (Instant)", "category": "Beverage", "buy_price": 280000, "margin": 0.38, "seasonal": "winter", "trend": "growing", "turnover": "fast", "volatility": "medium", "return_prone": False, "affinity": "all", "basket_group": "drink"},
    {"name": "Tea (Ahmad)", "category": "Beverage", "buy_price": 280000, "margin": 0.32, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "tea"},
    {"name": "Lentils", "category": "Staple", "buy_price": 220000, "margin": 0.15, "seasonal": "none", "trend": "stable", "turnover": "medium", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "legume"},
    {"name": "Chickpeas", "category": "Staple", "buy_price": 180000, "margin": 0.16, "seasonal": "none", "trend": "stable", "turnover": "medium", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "legume"},
    {"name": "Biscuits (Cream)", "category": "Snack", "buy_price": 45000, "margin": 0.42, "seasonal": "back_school", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "snack"},
    {"name": "Cheese (Feta)", "category": "Dairy", "buy_price": 280000, "margin": 0.24, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": True, "affinity": "all", "basket_group": "dairy"},
    {"name": "Flour (White)", "category": "Staple", "buy_price": 45000, "margin": 0.12, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "flour"},
    {"name": "Salt (Iodized)", "category": "Spice", "buy_price": 15000, "margin": 0.30, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "spice"},
    {"name": "Bread (Lavash)", "category": "Bakery", "buy_price": 25000, "margin": 0.25, "seasonal": "none", "trend": "stable", "turnover": "ultra_fast", "volatility": "low", "return_prone": True, "affinity": "all", "basket_group": "bread"},
    {"name": "Cream (Whipping)", "category": "Dairy", "buy_price": 180000, "margin": 0.28, "seasonal": "yalda", "trend": "spike", "turnover": "seasonal", "volatility": "medium", "return_prone": True, "affinity": "all", "basket_group": "dairy"},
    {"name": "Walnuts (Shelled)", "category": "Premium", "buy_price": 750000, "margin": 0.50, "seasonal": "yalda", "trend": "stable", "turnover": "slow", "volatility": "high", "return_prone": False, "affinity": "premium", "basket_group": "premium"},
    {"name": "Olive Oil (Extra Virgin)", "category": "Premium", "buy_price": 1200000, "margin": 0.60, "seasonal": "nowruz", "trend": "growing", "turnover": "slow", "volatility": "medium", "return_prone": False, "affinity": "premium", "basket_group": "oil"},
    {"name": "Frozen Vegetables", "category": "Frozen", "buy_price": 140000, "margin": 0.22, "seasonal": "winter", "trend": "growing", "turnover": "medium", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "frozen"},
    {"name": "Ice Cream (Vanilla)", "category": "Frozen", "buy_price": 280000, "margin": 0.35, "seasonal": "summer", "trend": "spike", "turnover": "seasonal", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "frozen"},
    {"name": "Couscous", "category": "Staple", "buy_price": 95000, "margin": 0.18, "seasonal": "none", "trend": "stable", "turnover": "slow", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "pasta"},
    {"name": "Kidney Beans", "category": "Staple", "buy_price": 125000, "margin": 0.16, "seasonal": "none", "trend": "stable", "turnover": "medium", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "legume"},
    {"name": "Tomato (Fresh)", "category": "Produce", "buy_price": 50000, "margin": 0.25, "seasonal": "summer", "trend": "spike", "turnover": "seasonal", "volatility": "high", "return_prone": True, "affinity": "all", "basket_group": "produce"},
    {"name": "Cucumber", "category": "Produce", "buy_price": 35000, "margin": 0.22, "seasonal": "summer", "trend": "spike", "turnover": "seasonal", "volatility": "high", "return_prone": True, "affinity": "all", "basket_group": "produce"},
    {"name": "Potato (5kg)", "category": "Produce", "buy_price": 120000, "margin": 0.18, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "medium", "return_prone": False, "affinity": "all", "basket_group": "produce"},
    {"name": "Onion (1kg)", "category": "Produce", "buy_price": 40000, "margin": 0.20, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "medium", "return_prone": False, "affinity": "all", "basket_group": "produce"},
    {"name": "Garlic (Fresh)", "category": "Produce", "buy_price": 180000, "margin": 0.30, "seasonal": "none", "trend": "stable", "turnover": "medium", "volatility": "low", "return_prone": False, "affinity": "all", "basket_group": "produce"},
    {"name": "Lemon", "category": "Produce", "buy_price": 60000, "margin": 0.28, "seasonal": "winter", "trend": "spike", "turnover": "seasonal", "volatility": "high", "return_prone": False, "affinity": "all", "basket_group": "produce"},
    {"name": "Orange", "category": "Produce", "buy_price": 50000, "margin": 0.25, "seasonal": "winter", "trend": "spike", "turnover": "seasonal", "volatility": "high", "return_prone": False, "affinity": "all", "basket_group": "produce"},
    {"name": "Apple (Red)", "category": "Produce", "buy_price": 70000, "margin": 0.30, "seasonal": "autumn", "trend": "spike", "turnover": "seasonal", "volatility": "high", "return_prone": False, "affinity": "all", "basket_group": "produce"},
    {"name": "Banana", "category": "Produce", "buy_price": 85000, "margin": 0.35, "seasonal": "none", "trend": "stable", "turnover": "fast", "volatility": "high", "return_prone": True, "affinity": "all", "basket_group": "produce"},
]

# Fill missing fields, compute sell_price, set is_dead default to False
for p in PRODUCT_TEMPLATES:
    p.setdefault("is_dead", False)
    p["sell_price"] = int(p["buy_price"] * (1 + p["margin"]))
    p["sell_price"] = round(p["sell_price"] / 1000) * 1000
    p["buy_price"] = round(p["buy_price"] / 1000) * 1000
    # Map seasonal string to month list
    season_map = {
        "none": [], "nowruz": [3,4], "yalda": [12], "nowruz+yalda": [3,4,12],
        "summer": [5,6,7,8], "winter": [11,12,1,2], "ramadan": [9],
        "back_school": [6,7], "autumn": [9,10,11], "spring": [3,4,5]
    }
    p["peak_months"] = season_map.get(p["seasonal"], [])
    p["seasonal"] = len(p["peak_months"]) > 0

# Ensure exactly 45 products (first 45 templates)
products_data = PRODUCT_TEMPLATES[:45]

def generate_products(seed=None):
    """Return the fixed product list (no randomness)."""
    if seed:
        random.seed(seed)  # for reproducibility of rest of generation
    # Assign extra attributes for compatibility
    for p in products_data:
        # Determine margin_type
        margin = p["margin"]
        if margin > 0.40:
            margin_type = "high"
        elif margin > 0.18:
            margin_type = "medium"
        elif margin > 0:
            margin_type = "low"
        else:
            margin_type = "negative"
        p["margin_type"] = margin_type
        p["popularity"] = {
            "ultra_fast": 0.95, "fast": 0.8, "medium": 0.6, "slow": 0.3,
            "seasonal": 0.5, "sporadic": 0.25, "dead": 0.05
        }.get(p["turnover"], 0.5)
        p["high_volatility"] = p["volatility"] in ["high", "very_high"]
        p["slow_moving"] = p["turnover"] in ["slow", "sporadic", "dead"]
    return products_data

# ============================================================================
# BASKET RULES (hand‑coded realistic pairs, high confidence)
# ============================================================================
BASKET_RULES = [
    ("Premium Basmati Rice", "Lentils", 0.78),
    ("Premium Basmati Rice", "Chickpeas", 0.65),
    ("Cooking Oil", "Tomato Paste", 0.72),
    ("Cooking Oil", "Onion", 0.58),
    ("Tea (Ahmad)", "Sugar", 0.85),
    ("Tea (Ahmad)", "Biscuits (Cream)", 0.62),
    ("Organic Chicken", "Cooking Oil", 0.70),
    ("Organic Chicken", "Tomato", 0.55),
    ("Yogurt", "Bread (Lavash)", 0.68),
    ("Butter (Premium)", "Jam", 0.71),
    ("Cheese (Feta)", "Bread (Lavash)", 0.75),
    ("Fresh Milk 1L", "Biscuits (Cream)", 0.60),
    ("Pasta", "Tomato Paste", 0.74),
    ("Pasta", "Cheese (Feta)", 0.52),
    ("Canned Tuna (Economy)", "Bread (Lavash)", 0.64),
    ("Coffee (Instant)", "Sugar", 0.77),
    ("Fresh Saffron", "Premium Basmati Rice", 0.82),
    ("Pistachios", "Tea (Ahmad)", 0.68),
    ("Summer Soft Drink", "Ice Cream (Vanilla)", 0.73),
    ("Loss Leader Rice", "Lentils", 0.70),
]
# Add a few random rules for variety (but still deterministic)
EXTRA_RULES = [
    ("Tomato Paste", "Pasta", 0.72),
    ("Eggs", "Butter (Premium)", 0.60),
    ("Flour (White)", "Sugar", 0.55),
    ("Walnuts (Shelled)", "Honey (Natural)", 0.65),
]
BASKET_RULES.extend(EXTRA_RULES)

def generate_basket_rules(products):
    """Return fixed basket rules (product names must exist)."""
    product_names = {p["name"] for p in products}
    valid = [(a,b,c) for a,b,c in BASKET_RULES if a in product_names and b in product_names]
    return valid[:60]

# ============================================================================
# PROMOTIONS – every month, product‑specific
# ============================================================================
def generate_promotions(products):
    promos = []
    # Monthly promotions based on real calendar events
    monthly_promos = {
        1: ("Winter Clearance", ["Canned Tuna (Economy)", "Pickles (Jar)"], 0.20),
        2: ("Valentine's", ["Honey (Natural)", "Dates"], 0.15),
        3: ("Nowruz", ["Premium Basmati Rice", "Fresh Saffron", "Fish"], 0.25),
        4: ("Nowruz continues", ["Pistachios", "Walnuts"], 0.20),
        5: ("Spring", ["Organic Chicken", "Yogurt"], 0.12),
        6: ("Back to School", ["Biscuits (Cream)", "Juice"], 0.18),
        7: ("Summer", ["Summer Soft Drink", "Ice Cream (Vanilla)"], 0.22),
        8: ("Summer", ["Tomato", "Cucumber"], 0.15),
        9: ("Ramadan", ["Dates", "Fresh Saffron", "Lentils"], 0.25),
        10: ("Autumn", ["Apple", "Walnuts"], 0.15),
        11: ("Black Friday", ["Coffee (Instant)", "Olive Oil"], 0.30),
        12: ("Yalda", ["Pistachios", "Watermelon", "Pomegranate"], 0.20),
    }
    for month, (_, prod_list, disc) in monthly_promos.items():
        for prod_name in prod_list:
            # only add if product exists
            if any(p["name"] == prod_name for p in products):
                promos.append((month, prod_name, disc))
    # Add random small promos for other products (low discount)
    for p in random.sample(products, min(10, len(products))):
        month = random.randint(1,12)
        disc = round(random.uniform(0.05, 0.12), 2)
        promos.append((month, p["name"], disc))
    return promos

# ============================================================================
# CUSTOMER SEGMENTS (unchanged, but with affinity logic later)
# ============================================================================
SEGMENT_CONFIG = {
    "VIP":        {"prob": 0.10, "avg_items": (4, 9), "return_rate": 0.02, "spend_mult": (1.6, 2.7), "freq_mult": (1.5, 2.2)},
    "Loyal":      {"prob": 0.25, "avg_items": (3, 7), "return_rate": 0.03, "spend_mult": (1.2, 1.9), "freq_mult": (1.2, 1.7)},
    "Regular":    {"prob": 0.35, "avg_items": (2, 5), "return_rate": 0.05, "spend_mult": (0.9, 1.4), "freq_mult": (0.8, 1.2)},
    "Occasional": {"prob": 0.20, "avg_items": (1, 3), "return_rate": 0.08, "spend_mult": (0.6, 1.0), "freq_mult": (0.4, 0.8)},
    "New":        {"prob": 0.10, "avg_items": (1, 2), "return_rate": 0.12, "spend_mult": (0.5, 0.8), "freq_mult": (0.2, 0.5)},
}
CUSTOMER_FIRST = ["Ali","Mohammad","Reza","Hossein","Ahmad","Sara","Maryam","Zahra","Fatemeh","Narges","Amir","Neda","Saman","Leila","Mehrdad","Shirin","Behnam","Roya"]
CUSTOMER_LAST = ["Ahmadi","Mohammadi","Karimi","Rezaei","Hosseini","Mousavi","Razavi","Nouri","Hashemi","Gholami","Moradi","Ebrahimi","Jafari","Kazemi","Rahimi"]

def generate_customers(n_customers=500, seed=None):
    if seed:
        random.seed(seed)
    customers = []
    seg_list = []
    for seg, cfg in SEGMENT_CONFIG.items():
        seg_list.extend([seg] * int(cfg["prob"] * 100))
    for i in range(1, n_customers + 1):
        first = random.choice(CUSTOMER_FIRST)
        last = random.choice(CUSTOMER_LAST)
        name = f"{first} {last}"
        segment = random.choice(seg_list)
        customers.append({
            "id": f"C{i:04d}",
            "name": name,
            "segment": segment,
            "first_purchase": None,
            "last_purchase": None,
            "total_spent": 0,
            "visit_count": 0,
        })
    return customers

# ============================================================================
# PERSIAN TRANSLATION (shortened for brevity, same as before)
# ============================================================================
PERSIAN_MAP = {
    "Rice": "برنج", "Oil": "روغن", "Sugar": "شکر", "Tea": "چای",
    "Pasta": "ماکارونی", "Lentils": "عدس", "Soda": "نوشابه", "Yogurt": "ماست",
    "Butter": "کره", "Jam": "مربا", "Pickles": "خیارشور", "Tuna": "تن ماهی",
    "Tomato Paste": "رب گوجه", "Cheese": "پنیر", "Biscuits": "بیسکویت",
    "Saffron": "زعفران", "Pistachios": "پسته", "Chicken": "مرغ", "Eggs": "تخم مرغ",
    "Flour": "آرد", "Salt": "نمک", "Honey": "عسل", "Coffee": "قهوه", "Milk": "شیر",
    "Bread": "نان", "Cream": "خامه", "Dates": "خرما", "Walnuts": "گردو",
    "Couscous": "کوسکوس", "Olive Oil": "روغن زیتون", "Chickpeas": "نخود",
    "Kidney Beans": "لوبیا قرمز", "Cucumber": "خیار", "Tomato": "گوجه",
    "Onion": "پیاز", "Potato": "سیب زمینی", "Garlic": "سیر", "Lemon": "لیمو",
    "Orange": "پرتقال", "Apple": "سیب", "Banana": "موز", "Ice Cream": "بستنی",
    "Cereal": "غلات", "Oats": "جو دوسر", "Premium": "ممتاز", "Super": "سوپر",
    "Golden": "طلایی", "Royal": "سلطنتی", "Fresh": "تازه", "Natural": "طبیعی",
    "Organic": "ارگانیک", "Selected": "انتخابی", "Fine": "مرغوب", "Deluxe": "لوکس",
    "Economy": "اقتصادی", "Family": "خانوادگی", "Jumbo": "غول", "Mini": "مینی",
    "Extra": "فوق", "Pure": "خالص", "Classic": "کلاسیک", "Traditional": "سنتی",
    "Loss Leader": "کم سود", "Zero Margin": "بدون سود", "Discontinued": "قطع شده",
}
TRANS_TYPE_FA = {"sale":"فروش","return_sale":"برگشت از فروش","purchase":"خرید","return_purchase":"برگشت از خرید"}
CATEGORY_FA = {"Staple":"غذایی","Beverage":"نوشیدنی","Dairy":"لبنیات","Canned":"کنسرو","Snack":"تنقلات","Premium":"لوکس","Meat":"پروتئین","Spice":"ادویه","Produce":"سبزیجات","Frozen":"یخ زده","Bakery":"نانوایی"}
SEGMENT_FA = {"VIP":"ویژه","Loyal":"وفادار","Regular":"عادی","Occasional":"موقت","New":"جدید","Supplier":"تامین کننده"}
def to_persian(text):
    if text is None or pd.isna(text): return ""
    text = str(text)
    for en, fa in PERSIAN_MAP.items():
        if en in text:
            text = text.replace(en, fa)
    return text

# ============================================================================
# MAIN GENERATOR – DELIBERATE, DEMAND‑BASED RESTOCKING
# ============================================================================
def make_invoices(n_invoices=18000, n_customers=500, shop_id=None, seed=42):
    random.seed(seed)
    np.random.seed(seed)
    print(f"\n{'='*70}\n  SALEYAR DELIBERATE ARCHETYPE GENERATOR\n{'='*70}")
    print(f"  Invoices: {n_invoices:,}   Customers: {n_customers}   Seed: {seed}\n")
    products = generate_products(seed)
    print(f"[1/5] Loaded {len(products)} deliberate products (dead: {sum(p['is_dead'] for p in products)})")
    customers = generate_customers(n_customers, seed)
    print("[2/5] Customers generated")
    basket_rules = generate_basket_rules(products)
    print(f"[3/5] Basket rules: {len(basket_rules)}")
    promotions = generate_promotions(products)
    print("[4/5] Promotions generated")
    print("[5/5] Generating transactions (2.5 years, demand‑based restock)...")

    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=910)  # 2.5 years
    date_range_days = 910
    product_dict = {p["name"]: p for p in products}

    # Stock tracking
    opening_stock = {p["name"]: random.randint(100, 600) for p in products}
    total_purchased = {p["name"]: 0 for p in products}
    total_return_sale = {p["name"]: 0 for p in products}
    total_sold = {p["name"]: 0 for p in products}
    total_return_purchase = {p["name"]: 0 for p in products}
    current_stock = opening_stock.copy()

    # Dead stock: only products with is_dead=True; they stop being restocked after cutoff
    dead_products = [p["name"] for p in products if p["is_dead"]]
    cutoff_date = start_date + timedelta(days=540)  # 1.5 years

    rows = []
    invoice_id = 10000
    date_weights = np.exp(np.linspace(0, 2, date_range_days))
    date_weights = date_weights / date_weights.sum()
    all_dates = [end_date - timedelta(days=i) for i in range(date_range_days)]

    # Precompute product demand scores for restocking (based on turnover)
    def demand_score(p):
        # higher score = restock more urgently
        base = {"ultra_fast": 10, "fast": 7, "medium": 4, "slow": 1, "seasonal": 3, "sporadic": 2, "dead": 0}
        return base.get(p["turnover"], 3)

    last_progress = 0
    for inv_idx in range(n_invoices):
        progress = int((inv_idx+1)/n_invoices*100)
        if progress >= last_progress+10:
            print(f"       → {progress}% complete", end="\r")
            last_progress = progress

        day_offset = np.random.choice(date_range_days, p=date_weights)
        date = all_dates[day_offset]
        is_after_deadline = date > cutoff_date

        # --- RESTOCKING (demand‑based) ---
        # Determine if any product needs restock (stock below threshold based on turnover)
        need_restock = False
        for p in products:
            stock = current_stock.get(p["name"], 0)
            threshold = 50 if p["turnover"] in ["fast","ultra_fast"] else 120 if p["turnover"] == "slow" else 80
            if stock < threshold:
                need_restock = True
                break
        if need_restock or random.random() < 0.10:
            # Choose product with highest demand score and low stock (weighted)
            candidates = []
            for p in products:
                if is_after_deadline and p["name"] in dead_products:
                    continue  # dead products no longer restocked
                stock = current_stock.get(p["name"], 0)
                if stock < 400:  # only if not overstocked
                    score = demand_score(p) * (1 - stock/600)  # lower stock = higher score
                    candidates.append((p, score))
            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)
                prod = candidates[0][0]
                stock_now = current_stock[prod["name"]]
                target = random.randint(400, 800) if prod["turnover"] in ["fast","ultra_fast"] else random.randint(200, 500)
                qty = max(40, target - stock_now)
                qty = min(qty, 1000)
                if qty > 0:
                    rows.append({"invoice_id":invoice_id,"date":date.strftime("%Y-%m-%d"),"product":prod["name"],"qty":qty,
                                 "buy_price":prod["buy_price"],"sell_price":0,"customer_id":"","customer_segment":"Supplier",
                                 "product_category":prod["category"],"transaction_type":"purchase"})
                    current_stock[prod["name"]] += qty
                    total_purchased[prod["name"]] += qty
                    invoice_id += 1

                # Return to supplier (small chance)
                if random.random() < 0.02:
                    ret_prod = random.choice([p for p in products if not (is_after_deadline and p["name"] in dead_products)])
                    ret_qty = random.randint(10, 40)
                    if current_stock.get(ret_prod["name"],0) >= ret_qty:
                        rows.append({"invoice_id":invoice_id,"date":date.strftime("%Y-%m-%d"),"product":ret_prod["name"],"qty":ret_qty,
                                     "buy_price":ret_prod["buy_price"],"sell_price":0,"customer_id":"","customer_segment":"Supplier",
                                     "product_category":ret_prod["category"],"transaction_type":"return_purchase"})
                        current_stock[ret_prod["name"]] -= ret_qty
                        total_return_purchase[ret_prod["name"]] += ret_qty
                        invoice_id += 1

        # --- CUSTOMER SELECTION ---
        customer = random.choice(customers)
        seg = customer["segment"]
        seg_cfg = SEGMENT_CONFIG[seg]
        if customer["first_purchase"] is None:
            customer["first_purchase"] = date
        customer["last_purchase"] = date
        customer["visit_count"] += 1

        min_items, max_items = seg_cfg["avg_items"]
        n_items = random.randint(min_items, max_items)

        # --- SELECT PRODUCTS with affinity (premium products for VIP/Loyal) ---
        selected = []
        # Filter available products (skip dead after deadline)
        live_products = [p for p in products if not (is_after_deadline and p["name"] in dead_products)]
        if not live_products:
            live_products = products
        # Weight products by popularity and affinity
        weights = []
        for p in live_products:
            w = p["popularity"]
            # Affinity: premium products weighted more for VIP/Loyal
            if p.get("affinity") == "premium" and seg in ["VIP","Loyal"]:
                w *= 2.5
            elif p.get("affinity") == "premium" and seg not in ["VIP","Loyal"]:
                w *= 0.3
            # Seasonal boost in peak months
            if p["seasonal"] and date.month in p["peak_months"]:
                w *= 2.0
            weights.append(w)
        anchor = random.choices(live_products, weights=weights, k=1)[0]
        selected.append(anchor["name"])

        # Add basket rules
        for a, b, conf in basket_rules:
            if len(selected) >= n_items:
                break
            if anchor["name"] == a and random.random() < conf and b not in selected:
                selected.append(b)
            elif anchor["name"] == b and random.random() < conf and a not in selected:
                selected.append(a)

        # Fill remaining randomly (respecting affinity)
        remaining = n_items - len(selected)
        if remaining > 0:
            pool = [p for p in live_products if p["name"] not in selected]
            if pool:
                # Weight pool by affinity again
                pool_weights = []
                for p in pool:
                    w = 1.0
                    if p.get("affinity") == "premium" and seg in ["VIP","Loyal"]:
                        w = 3.0
                    elif p.get("affinity") == "premium":
                        w = 0.2
                    pool_weights.append(w)
                extra = random.choices(pool, weights=pool_weights, k=min(remaining, len(pool)))
                selected.extend([e["name"] for e in extra])

        # --- GENERATE ROWS ---
        for prod_name in selected:
            product = product_dict[prod_name]
            stock = current_stock.get(prod_name, 0)
            if stock <= 0:
                continue

            # Base quantity from segment
            base_qty = max(1, int(np.random.normal(n_items, 1.5)))
            # Seasonality boost
            if product["seasonal"] and date.month in product["peak_months"]:
                base_qty = int(base_qty * random.uniform(1.8, 3.0))
            # Trend effect (growing/declining)
            days_since_start = (date - start_date).days
            if product["trend"] == "growing":
                base_qty = int(base_qty * (1 + days_since_start / 910 * 0.8))
            elif product["trend"] == "declining":
                base_qty = int(base_qty * (1 - days_since_start / 910 * 0.7))
                base_qty = max(1, base_qty)
            elif product["trend"] == "spike" and date.month in product["peak_months"]:
                base_qty = int(base_qty * random.uniform(2.0, 3.5))

            spend_min, spend_max = seg_cfg["spend_mult"]
            qty = max(1, int(base_qty * random.uniform(spend_min, spend_max)))
            qty = min(qty, stock)

            # Price variation
            if product["high_volatility"]:
                price_var = random.uniform(0.85, 1.20)
            else:
                price_var = random.uniform(0.94, 1.07)
            sell_price = int(product["sell_price"] * price_var)
            sell_price = round(sell_price / 1000) * 1000
            if sell_price < 1000:
                sell_price = 1000

            # Promotion discount
            for month, prod, disc in promotions:
                if prod == prod_name and date.month == month:
                    sell_price = int(sell_price * (1 - disc))

            # Transaction type
            rand = random.random()
            return_rate = seg_cfg["return_rate"]
            if product.get("return_prone", False):
                return_rate += 0.07
            if rand < return_rate:
                trans_type = "return_sale"
                return_qty = min(qty, max(1, stock // 5))
                current_stock[prod_name] += return_qty
                total_return_sale[prod_name] += return_qty
                qty = return_qty
                sell_price = 0
            else:
                trans_type = "sale"
                current_stock[prod_name] -= qty
                total_sold[prod_name] += qty
                customer["total_spent"] += sell_price * qty

            if qty == 0:
                continue

            rows.append({
                "invoice_id": invoice_id,
                "date": date.strftime("%Y-%m-%d"),
                "product": prod_name,
                "qty": qty,
                "buy_price": product["buy_price"],
                "sell_price": sell_price,
                "customer_id": customer["id"],
                "customer_segment": seg,
                "product_category": product["category"],
                "transaction_type": trans_type,
            })

        invoice_id += random.randint(1, 3)

    print("\n       → 100% complete. Finalizing...")
    df = pd.DataFrame(rows)

    # Add missing values (0.2%)
    for col in ["customer_id", "product"]:
        mask = np.random.random(len(df)) < 0.002
        df.loc[mask, col] = None

    # Stock verification
    print(f"\n{'='*70}\n  STOCK VERIFICATION\n{'='*70}")
    mismatches = 0
    for p in products:
        name = p["name"]
        opening = opening_stock[name]
        added = total_purchased[name] + total_return_sale[name]
        removed = total_sold[name] + total_return_purchase[name]
        calc = opening + added - removed
        actual = current_stock[name]
        if calc != actual:
            mismatches += 1
    if mismatches == 0:
        print(f"  ✅ PERFECT MATCH: All {len(products)} products verified")
    else:
        print(f"  ⚠️ WARNING: {mismatches} mismatches (should be 0)")

    # Summary
    print(f"\n{'='*70}\n  GENERATION SUMMARY\n{'='*70}")
    print(f"  Total rows:       {len(df):,}")
    print(f"  Sales:            {(df['transaction_type'] == 'sale').sum():,}")
    print(f"  Return Sales:     {(df['transaction_type'] == 'return_sale').sum():,}")
    print(f"  Purchases:        {(df['transaction_type'] == 'purchase').sum():,}")
    print(f"  Return Purchases: {(df['transaction_type'] == 'return_purchase').sum():,}")
    print(f"  Unique products:  {df['product'].nunique()}")
    print(f"  Unique customers: {df['customer_id'].nunique()}")
    print(f"  Date range:       {df['date'].min()} to {df['date'].max()}")
    print(f"{'='*70}\n")
    return df

def make_persian(df_en):
    df = df_en.copy()
    df["product"] = df["product"].apply(to_persian)
    df["transaction_type"] = df["transaction_type"].map(TRANS_TYPE_FA).fillna(df["transaction_type"])
    df["product_category"] = df["product_category"].map(CATEGORY_FA).fillna(df["product_category"])
    df["customer_segment"] = df["customer_segment"].map(SEGMENT_FA).fillna(df["customer_segment"])
    df = df.rename(columns={
        "invoice_id": "شماره فاکتور", "date": "تاریخ", "product": "نام کالا",
        "qty": "تعداد", "buy_price": "قیمت خرید", "sell_price": "قیمت فروش",
        "customer_id": "کد مشتری", "customer_segment": "بخش مشتری",
        "product_category": "دسته‌بندی", "transaction_type": "نوع تراکنش",
    })
    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoices", type=int, default=20000)
    parser.add_argument("--customers", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=82)
    args = parser.parse_args()
    os.makedirs("data", exist_ok=True)
    clean_old_files()
    df_en = make_invoices(n_invoices=args.invoices, n_customers=args.customers, seed=args.seed)
    df_en.to_csv("data/sample_en.csv", index=False, encoding="utf-8")
    print(f"[OK] Saved: data/sample_en.csv ({len(df_en):,} rows)")
    df_fa = make_persian(df_en)
    df_fa.to_csv("data/sample_fa.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] Saved: data/sample_fa.csv (Persian version)")
    print("\n" + "="*70 + "\n  READY TO TEST SALEYAR PIPELINE\n" + "="*70 + "\n  ▶ Run: python run.py --terminal\n  ▶ Upload: data/sample_en.csv\n  ▶ Verify stock: data/sample_stock.csv\n" + "="*70 + "\n")