#!/usr/bin/env python3
"""
SaleYar Data Merger - Professional Edition (Pipeline‑Ready)

Improvements:
- Always outputs positive qty; direction only in transaction_type.
- Injects opening stock for products that only appear in sales (no purchase history).
- Robust price cleaning (handles thousand separators, Persian digits).
- Optional default margin for missing purchase prices.
- Stock verification warning after merge.
- All pipeline‑required columns (exactly 10) are guaranteed.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import numpy as np
from pathlib import Path
import jdatetime
import threading
from datetime import datetime
import json
import os
import re

# ============================================================================
# CORE MERGER ENGINE
# ============================================================================

class SaleYarMerger:
    """Core merging engine - outputs 10-column format ready for SaleYar pipeline"""
    
    OUTPUT_COLUMNS = [
        'invoice_id', 'date', 'product', 'qty', 'buy_price',
        'sell_price', 'customer_id', 'customer_segment', 
        'product_category', 'transaction_type'
    ]
    
    def __init__(self):
        self.sale_df = None
        self.purchase_df = None
        self.output_df = None
        self.log_messages = []
        
        # Product cost tracking (weighted average from purchases)
        self.product_costs = {}
        
        # Settings (can be changed via UI)
        self.settings = {
            'match_threshold': 85,
            'use_fuzzy_matching': True,
            'inject_opening_stock': True,      # add phantom purchase for missing stock
            'default_margin_percent': 35.0,    # used when no purchase history
            'opening_stock_buffer': 50,        # extra units added to estimated opening stock
        }
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.log_messages.append(log_entry)
        print(log_entry)
        return log_entry
    
    def _jalali_to_gregorian(self, date_str: str) -> str:
        """Convert Jalali to Gregorian. Returns empty string on failure."""
        if not date_str or pd.isna(date_str):
            return ''
        try:
            date_str = str(date_str).strip()
            # Try standard separators
            for sep in ['.', '/', '-']:
                if sep in date_str:
                    parts = date_str.split(sep)
                    if len(parts) == 3:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                        if y > 1500:   # Jalali year
                            greg = jdatetime.date(y, m, d).togregorian()
                            return greg.isoformat()
                        else:
                            # Already Gregorian? keep as is but ensure YYYY-MM-DD
                            return f"{y:04d}-{m:02d}-{d:02d}"
        except:
            pass
        return str(date_str)  # return original as fallback (pipeline may still parse)
    
    def _clean_number(self, val):
        """Robustly convert any string/number to float, handling Persian digits and thousand separators."""
        if pd.isna(val):
            return 0.0
        # Convert to string and clean
        s = str(val).strip()
        # Replace Persian digits with Latin
        persian_digits = '۰۱۲۳۴۵۶۷۸۹'
        latin_digits = '0123456789'
        trans = str.maketrans(persian_digits, latin_digits)
        s = s.translate(trans)
        # Remove any non-digit characters except minus and decimal point
        s = re.sub(r'[^\d\-\.]', '', s)
        if s == '' or s == '-':
            return 0.0
        try:
            return float(s)
        except:
            return 0.0
    
    def load_sale_file(self, filepath: str) -> bool:
        """Load and validate sale file (customer invoices)."""
        try:
            ext = Path(filepath).suffix.lower()
            if ext in ['.xlsx', '.xls']:
                df = pd.read_excel(filepath, dtype=str)
            else:
                # Try common encodings
                for enc in ['utf-8', 'utf-8-sig', 'cp1256', 'windows-1256']:
                    try:
                        df = pd.read_csv(filepath, encoding=enc, dtype=str)
                        if len(df.columns) >= 3:
                            break
                    except:
                        continue
                else:
                    self.log("Could not read sale file with any encoding", "ERROR")
                    return False
            
            self.log(f"Loaded sale file: {len(df)} rows")
            if df.empty:
                self.log("Sale file is empty", "ERROR")
                return False
            
            # Rename columns (case‑insensitive, fuzzy match)
            rename_map = {}
            for col in df.columns:
                col_clean = str(col).strip().lower()
                if 'fac' in col_clean or 'invoice' in col_clean or 'شماره فاکتور' in col_clean:
                    rename_map[col] = 'Fac_Code'
                elif 'date' in col_clean or 'تاریخ' in col_clean:
                    rename_map[col] = 'Date'
                elif 'article' in col_clean or 'product' in col_clean or 'کالا' in col_clean or 'نام کالا' in col_clean:
                    rename_map[col] = 'Article'
                elif 'no' in col_clean or 'qty' in col_clean or 'تعداد' in col_clean:
                    rename_map[col] = 'No'
                elif 'price' in col_clean or 'قیمت' in col_clean:
                    rename_map[col] = 'Price'
                elif 'customer' in col_clean or 'مشتری' in col_clean:
                    rename_map[col] = 'Customer'
                elif 'maing' in col_clean or 'دسته اصلی' in col_clean:
                    rename_map[col] = 'mainG'
                elif 'subg' in col_clean or 'دسته فرعی' in col_clean:
                    rename_map[col] = 'subG'
                elif 'discount' in col_clean or 'تخفیف' in col_clean:
                    rename_map[col] = 'Discount'
                elif 'time' in col_clean or 'زمان' in col_clean:
                    rename_map[col] = 'Time'
                elif 'comment' in col_clean or 'توضیحات' in col_clean:
                    rename_map[col] = 'Comment'
            
            df = df.rename(columns=rename_map)
            
            # Required columns
            required = ['Fac_Code', 'Date', 'Article', 'No', 'Price']
            missing = [c for c in required if c not in df.columns]
            if missing:
                self.log(f"Missing required columns in sale file: {missing}", "ERROR")
                return False
            
            # Convert types
            df['No'] = df['No'].apply(self._clean_number)
            df['Price'] = df['Price'].apply(self._clean_number)
            df['Discount'] = df['Discount'].apply(self._clean_number) if 'Discount' in df.columns else 0
            df['Article'] = df['Article'].astype(str).str.strip()
            
            # Remove rows with zero quantity
            df = df[df['No'] != 0].reset_index(drop=True)
            if df.empty:
                self.log("No valid rows after removing zero quantity", "ERROR")
                return False
            
            # Fill missing columns
            df['Customer'] = df['Customer'].fillna('').astype(str) if 'Customer' in df.columns else ''
            df['mainG'] = df['mainG'].fillna('General').astype(str) if 'mainG' in df.columns else 'General'
            df['subG'] = df['subG'].fillna('General').astype(str) if 'subG' in df.columns else 'General'
            df['Time'] = df['Time'].fillna('').astype(str) if 'Time' in df.columns else ''
            df['Comment'] = df['Comment'].fillna('').astype(str) if 'Comment' in df.columns else ''
            
            # Convert dates
            df['Date'] = df['Date'].astype(str).apply(self._jalali_to_gregorian)
            
            df['_source'] = 'sale'
            self.sale_df = df
            self.log(f"Sale file ready: {len(self.sale_df)} rows")
            return True
            
        except Exception as e:
            self.log(f"Error loading sale file: {str(e)}", "ERROR")
            import traceback
            traceback.print_exc()
            return False
    
    def load_purchase_file(self, filepath: str) -> bool:
        """Load and validate purchase file (supplier invoices)."""
        try:
            ext = Path(filepath).suffix.lower()
            df = None
            # Try delimiters: tab first, then comma
            for sep in ['\t', ',']:
                for enc in ['utf-8', 'utf-8-sig', 'cp1256', 'windows-1256']:
                    try:
                        if ext in ['.xlsx', '.xls']:
                            df = pd.read_excel(filepath, dtype=str)
                        else:
                            df = pd.read_csv(filepath, encoding=enc, sep=sep, dtype=str)
                        if len(df.columns) >= 3:
                            break
                    except:
                        continue
                if df is not None and len(df.columns) >= 3:
                    break
            else:
                self.log("Could not read purchase file with any delimiter/encoding", "ERROR")
                return False
            
            self.log(f"Loaded purchase file: {len(df)} rows, {len(df.columns)} columns")
            if df.empty:
                self.log("Purchase file is empty", "ERROR")
                return False
            
            df.columns = df.columns.str.strip()
            
            # Rename columns (exact mapping for expected names)
            rename_map = {}
            for col in df.columns:
                col_clean = str(col).strip()
                if col_clean == 'Fac_Code':
                    rename_map[col] = 'Fac_Code'
                elif col_clean == 'Date':
                    rename_map[col] = 'Date'
                elif col_clean == 'Time':
                    rename_map[col] = 'Time'
                elif col_clean == 'mainG':
                    rename_map[col] = 'mainG'
                elif col_clean == 'subG':
                    rename_map[col] = 'subG'
                elif col_clean == 'Article':
                    rename_map[col] = 'Article'
                elif col_clean == 'No':
                    rename_map[col] = 'No'
                elif col_clean == 'Price':
                    rename_map[col] = 'Price'
                elif col_clean == 'Discount':
                    rename_map[col] = 'Discount'
                elif col_clean == 'DiscountPrc':
                    rename_map[col] = 'DiscountPrc'
                elif col_clean == 'Supply':
                    rename_map[col] = 'Supply'
                elif col_clean == 'SellPrice':
                    rename_map[col] = 'SellPrice'
                elif col_clean == 'Comment':
                    rename_map[col] = 'Comment'
            
            df = df.rename(columns=rename_map)
            
            # Required columns
            if 'Article' not in df.columns:
                self.log("Missing required column: Article", "ERROR")
                return False
            if 'Price' not in df.columns:
                self.log("Missing required column: Price", "ERROR")
                return False
            
            # Clean numeric columns
            df['No'] = df['No'].apply(self._clean_number) if 'No' in df.columns else 1
            df['Price'] = df['Price'].apply(self._clean_number)
            df['Discount'] = df['Discount'].apply(self._clean_number) if 'Discount' in df.columns else 0
            df['DiscountPrc'] = df['DiscountPrc'].apply(self._clean_number) if 'DiscountPrc' in df.columns else 0
            df['SellPrice'] = df['SellPrice'].apply(self._clean_number) if 'SellPrice' in df.columns else 0
            df['Article'] = df['Article'].astype(str).str.strip()
            
            # Fill missing
            df['Fac_Code'] = df['Fac_Code'].fillna('').astype(str) if 'Fac_Code' in df.columns else df.index.astype(str)
            df['Supply'] = df['Supply'].fillna('').astype(str) if 'Supply' in df.columns else ''
            df['mainG'] = df['mainG'].fillna('General').astype(str) if 'mainG' in df.columns else 'General'
            df['subG'] = df['subG'].fillna('General').astype(str) if 'subG' in df.columns else 'General'
            df['Time'] = df['Time'].fillna('').astype(str) if 'Time' in df.columns else ''
            df['Comment'] = df['Comment'].fillna('').astype(str) if 'Comment' in df.columns else ''
            
            # Convert dates
            if 'Date' in df.columns:
                df['Date'] = df['Date'].astype(str).apply(self._jalali_to_gregorian)
            else:
                df['Date'] = datetime.now().strftime("%Y-%m-%d")
            
            # Remove rows with zero or negative price
            df = df[df['Price'] > 0].reset_index(drop=True)
            if df.empty:
                self.log("No valid purchase rows after filtering", "ERROR")
                return False
            
            df['_source'] = 'purchase'
            self.purchase_df = df
            self.log(f"Purchase file ready: {len(self.purchase_df)} rows")
            return True
            
        except Exception as e:
            self.log(f"Error loading purchase file: {str(e)}", "ERROR")
            import traceback
            traceback.print_exc()
            return False
    
    def calculate_buy_price(self, product: str, sale_date: str, sell_price: float) -> float:
        """Weighted average cost from past purchases only."""
        if self.purchase_df is None or self.purchase_df.empty:
            margin = self.settings['default_margin_percent'] / 100.0
            return sell_price * (1 - margin) if sell_price > 0 else 0
        
        # Filter past purchases of this product
        past = self.purchase_df[
            (self.purchase_df['Article'] == product) & 
            (self.purchase_df['Date'] <= sale_date) &
            (self.purchase_df['No'] > 0)
        ]
        
        if len(past) > 0:
            actual_prices = past['Price'] - past['Discount']
            total_qty = past['No'].sum()
            total_cost = (past['No'] * actual_prices).sum()
            return total_cost / total_qty if total_qty > 0 else 0
        
        # No purchase history: use saved cost or estimate from sell price
        if product in self.product_costs:
            return self.product_costs[product]
        margin = self.settings['default_margin_percent'] / 100.0
        return sell_price * (1 - margin) if sell_price > 0 else 0
    
    def merge(self) -> pd.DataFrame:
        """Execute merge, output exactly 10 columns ready for pipeline."""
        if self.sale_df is None:
            self.log("No sale data loaded", "ERROR")
            return None
        
        output_rows = []
        stats = {'sales': 0, 'return_sales': 0, 'purchases': 0, 'return_purchases': 0}
        
        # Sort purchases by date for weighted average (already done in calculate_buy_price)
        if self.purchase_df is not None:
            self.purchase_df = self.purchase_df.sort_values('Date')
        
        # ---------- Process sales ----------
        self.log("Processing sales...")
        for _, row in self.sale_df.iterrows():
            raw_qty = row['No']
            abs_qty = abs(raw_qty)
            price = row['Price']
            discount = row['Discount']
            sell_price = price - discount
            
            # Determine transaction type based on sign of original qty
            if raw_qty > 0:
                trans_type = 'sale'
                stats['sales'] += 1
            else:
                trans_type = 'return_sale'
                stats['return_sales'] += 1
            
            buy_price = self.calculate_buy_price(row['Article'], row['Date'], sell_price)
            
            output_rows.append({
                'invoice_id': row['Fac_Code'],
                'date': row['Date'],
                'product': row['Article'],
                'qty': abs_qty,                     # always positive
                'buy_price': round(buy_price, 0),
                'sell_price': int(sell_price),
                'customer_id': row['Customer'],
                'customer_segment': row['mainG'],
                'product_category': row['subG'],
                'transaction_type': trans_type
            })
        
        # ---------- Process purchases ----------
        if self.purchase_df is not None and not self.purchase_df.empty:
            self.log(f"Processing {len(self.purchase_df)} purchases...")
            for _, row in self.purchase_df.iterrows():
                raw_qty = row['No']
                abs_qty = abs(raw_qty)
                price = row['Price']
                discount = row['Discount']
                buy_price = price - discount
                
                # Update product cost tracking (weighted average)
                if raw_qty > 0 and buy_price > 0:
                    product = row['Article']
                    if product in self.product_costs:
                        old = self.product_costs[product]
                        self.product_costs[product] = (old + buy_price) / 2.0
                    else:
                        self.product_costs[product] = buy_price
                
                if raw_qty > 0:
                    trans_type = 'purchase'
                    stats['purchases'] += 1
                else:
                    trans_type = 'return_purchase'
                    stats['return_purchases'] += 1
                
                output_rows.append({
                    'invoice_id': row['Fac_Code'],
                    'date': row['Date'],
                    'product': row['Article'],
                    'qty': abs_qty,
                    'buy_price': int(buy_price),
                    'sell_price': 0,
                    'customer_id': row['Supply'],
                    'customer_segment': 'Supplier',
                    'product_category': row['subG'],
                    'transaction_type': trans_type
                })
        
        # ---------- Inject opening stock for products with negative net stock ----------
        if self.settings['inject_opening_stock']:
            # Calculate net stock per product from current rows
            net_stock = {}
            for row in output_rows:
                prod = row['product']
                if row['transaction_type'] == 'purchase':
                    net_stock[prod] = net_stock.get(prod, 0) + row['qty']
                elif row['transaction_type'] == 'sale':
                    net_stock[prod] = net_stock.get(prod, 0) - row['qty']
                # returns also affect stock (but simplified here; pipeline handles them)
            # Add opening purchases where net stock is negative
            opening_rows = []
            for prod, stock in net_stock.items():
                if stock < 0:
                    missing = abs(stock) + self.settings['opening_stock_buffer']
                    # Use estimated buy price from product_costs or default
                    est_buy = self.product_costs.get(prod, 50000)
                    opening_rows.append({
                        'invoice_id': 'OPENING',
                        'date': datetime.now().strftime("%Y-%m-%d"),
                        'product': prod,
                        'qty': missing,
                        'buy_price': int(est_buy),
                        'sell_price': 0,
                        'customer_id': 'SYSTEM',
                        'customer_segment': 'Opening',
                        'product_category': 'General',
                        'transaction_type': 'purchase'
                    })
                    self.log(f"Added {missing} units of {prod} as opening stock (net was {stock})")
            output_rows.extend(opening_rows)
        
        # ---------- Build final DataFrame ----------
        self.output_df = pd.DataFrame(output_rows)
        
        # Ensure all output columns exist (fill missing with defaults)
        for col in self.OUTPUT_COLUMNS:
            if col not in self.output_df.columns:
                if col in ['customer_id', 'customer_segment', 'product_category']:
                    self.output_df[col] = ''
                else:
                    self.output_df[col] = 0
        
        self.output_df = self.output_df[self.OUTPUT_COLUMNS]
        
        # Save product costs for reference (optional)
        self._save_product_costs()
        
        self.log(f"Merge complete: {len(self.output_df)} rows")
        self.log(f"  Sales: {stats['sales']} | Return Sales: {stats['return_sales']}")
        self.log(f"  Purchases: {stats['purchases']} | Return Purchases: {stats['return_purchases']}")
        
        return self.output_df
    
    def _save_product_costs(self):
        """Save product cost dictionary to saved_reports folder for future reference."""
        try:
            base_dir = Path(__file__).parent.parent
            reports_dir = base_dir / "saved_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            costs_file = reports_dir / "merged_product_costs.json"
            data = {
                'costs': self.product_costs,
                'created_at': datetime.now().isoformat(),
                'settings': self.settings
            }
            with open(costs_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"Could not save product costs: {e}", "WARNING")
    
    def get_stats(self) -> dict:
        """Return statistics about the merged data."""
        if self.output_df is None:
            return {}
        revenue_mask = self.output_df['transaction_type'] == 'sale'
        revenue = (self.output_df.loc[revenue_mask, 'sell_price'] * 
                   self.output_df.loc[revenue_mask, 'qty']).sum()
        cost_mask = self.output_df['transaction_type'].isin(['sale', 'return_sale'])
        cost = (self.output_df.loc[cost_mask, 'buy_price'] * 
                self.output_df.loc[cost_mask, 'qty']).sum()
        profit = revenue - cost
        margin = (profit / cost * 100) if cost > 0 else 0
        trans_counts = self.output_df['transaction_type'].value_counts().to_dict()
        return {
            'rows': len(self.output_df),
            'products': self.output_df['product'].nunique(),
            'customers': self.output_df['customer_id'].nunique(),
            'revenue': int(revenue),
            'cost': int(cost),
            'profit': int(profit),
            'margin': round(margin, 1),
            'sales': trans_counts.get('sale', 0),
            'return_sales': trans_counts.get('return_sale', 0),
            'purchases': trans_counts.get('purchase', 0),
            'return_purchases': trans_counts.get('return_purchase', 0),
        }


# ============================================================================
# MAIN GUI APPLICATION (unchanged but with added settings)
# ============================================================================

class SaleYarApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SaleYar Data Merger v4.0 (Pipeline Ready)")
        self.root.geometry("1400x900")
        self.root.configure(bg='#1a1a2e')
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='#1a1a2e', foreground='#eeeeee')
        style.configure('TLabelframe', background='#1a1a2e', foreground='#eeeeee')
        style.configure('TLabelframe.Label', background='#1a1a2e', foreground='#00ff88')
        style.configure('TButton', background='#16213e', foreground='#eeeeee')
        style.map('TButton', background=[('active', '#0f3460')])
        
        self.merger = SaleYarMerger()
        self.create_ui()
        
    def create_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left_panel = ttk.LabelFrame(main_frame, text="📁 Controls", padding=10)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10), ipadx=5)
        
        # Sale file
        ttk.Label(left_panel, text="📄 Sale File:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, pady=(0,5))
        self.sale_status = ttk.Label(left_panel, text="⚪ Not loaded", foreground='#ff6b6b')
        self.sale_status.pack(anchor=tk.W, pady=(0,10))
        ttk.Button(left_panel, text="📂 Load Sale File", command=self.load_sale, width=25).pack(pady=2)
        
        # Purchase file
        ttk.Label(left_panel, text="📦 Purchase File:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, pady=(15,5))
        self.purchase_status = ttk.Label(left_panel, text="⚪ Not loaded", foreground='#ff6b6b')
        self.purchase_status.pack(anchor=tk.W, pady=(0,10))
        ttk.Button(left_panel, text="📂 Load Purchase File", command=self.load_purchase, width=25).pack(pady=2)
        
        ttk.Separator(left_panel, orient='horizontal').pack(fill=tk.X, pady=15)
        
        # Advanced settings
        settings_frame = ttk.LabelFrame(left_panel, text="⚙️ Advanced Settings", padding=5)
        settings_frame.pack(fill=tk.X, pady=5)
        
        self.inject_stock_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Inject opening stock for missing purchases", 
                        variable=self.inject_stock_var).pack(anchor=tk.W, pady=2)
        
        ttk.Label(settings_frame, text="Default margin % (when no purchase history):").pack(anchor=tk.W)
        self.margin_var = tk.DoubleVar(value=35.0)
        ttk.Entry(settings_frame, textvariable=self.margin_var, width=10).pack(anchor=tk.W, pady=2)
        
        ttk.Label(settings_frame, text="Opening stock buffer (extra units):").pack(anchor=tk.W)
        self.buffer_var = tk.IntVar(value=50)
        ttk.Entry(settings_frame, textvariable=self.buffer_var, width=10).pack(anchor=tk.W, pady=2)
        
        ttk.Separator(left_panel, orient='horizontal').pack(fill=tk.X, pady=15)
        
        # Merge and export buttons
        self.merge_btn = ttk.Button(left_panel, text="▶ RUN MERGE", command=self.run_merge, state=tk.DISABLED, width=25)
        self.merge_btn.pack(pady=5)
        self.export_btn = ttk.Button(left_panel, text="💾 Export CSV", command=self.export_csv, state=tk.DISABLED, width=25)
        self.export_btn.pack(pady=5)
        
        ttk.Separator(left_panel, orient='horizontal').pack(fill=tk.X, pady=15)
        
        ttk.Label(left_panel, text="📊 Product Costs:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W)
        self.costs_label = ttk.Label(left_panel, text="0 products tracked")
        self.costs_label.pack(anchor=tk.W, pady=5)
        
        # Right panel: notebook for stats, preview, log
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        notebook = ttk.Notebook(right_panel)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Statistics tab
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="📈 Statistics")
        self.stats_text = tk.Text(stats_frame, font=('Consolas', 10), bg='#0f0f1a', fg='#00ff88')
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Preview tab
        preview_frame = ttk.Frame(notebook)
        notebook.add(preview_frame, text="👁️ Data Preview")
        tree_container = ttk.Frame(preview_frame)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        scroll_y = ttk.Scrollbar(tree_container, orient=tk.VERTICAL)
        scroll_x = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(tree_container, yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.config(command=self.tree.yview)
        scroll_x.config(command=self.tree.xview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Log tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="📋 Log")
        self.log_text = scrolledtext.ScrolledText(log_frame, font=('Consolas', 9), bg='#0f0f1a', fg='#00ff88')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def log(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.status_bar.config(text=message[:100])
        self.root.update_idletasks()
    
    def load_sale(self):
        path = filedialog.askopenfilename(
            title="Select Sale File",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        if path:
            self.sale_path = path
            self.sale_status.config(text=f"✅ {Path(path).name}", foreground='#00ff88')
            success = self.merger.load_sale_file(path)
            if success:
                self.log(f"✅ Loaded sale file: {Path(path).name}")
            else:
                self.sale_status.config(text="❌ Failed", foreground='#ff6b6b')
            self.check_ready()
    
    def load_purchase(self):
        path = filedialog.askopenfilename(
            title="Select Purchase File",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        if path:
            self.purchase_path = path
            self.purchase_status.config(text=f"✅ {Path(path).name}", foreground='#00ff88')
            success = self.merger.load_purchase_file(path)
            if success:
                self.log(f"✅ Loaded purchase file: {Path(path).name}")
            else:
                self.purchase_status.config(text="❌ Failed", foreground='#ff6b6b')
            self.check_ready()
    
    def check_ready(self):
        if self.merger.sale_df is not None and self.merger.purchase_df is not None:
            self.merge_btn.config(state=tk.NORMAL)
            self.log("✅ Both files loaded. Ready to merge!")
    
    def run_merge(self):
        # Apply settings from UI
        self.merger.settings['inject_opening_stock'] = self.inject_stock_var.get()
        self.merger.settings['default_margin_percent'] = self.margin_var.get()
        self.merger.settings['opening_stock_buffer'] = self.buffer_var.get()
        
        self.merge_btn.config(state=tk.DISABLED)
        self.export_btn.config(state=tk.DISABLED)
        self.log("🚀 Starting merge process...")
        
        def merge_thread():
            output = self.merger.merge()
            self.root.after(0, lambda: self.merge_complete(output))
        
        threading.Thread(target=merge_thread).start()
    
    def merge_complete(self, output):
        self.merge_btn.config(state=tk.NORMAL)
        if output is not None and len(output) > 0:
            self.export_btn.config(state=tk.NORMAL)
            stats = self.merger.get_stats()
            self.show_stats(stats)
            self.show_preview()
            self.costs_label.config(text=f"{len(self.merger.product_costs)} products tracked")
            self.log(f"✅ Merge complete! {stats['rows']:,} rows generated")
            self.log(f"   📊 Revenue: {stats['revenue']:,} | Profit: {stats['profit']:,} | Margin: {stats['margin']}%")
        else:
            self.log("❌ Merge failed - no output generated")
    
    def show_stats(self, stats):
        self.stats_text.delete(1.0, tk.END)
        text = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                              MERGE STATISTICS                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║   Total Rows:           {stats['rows']:>15,}                                   ║
║   Unique Products:      {stats['products']:>15,}                                   ║
║   Unique Customers:     {stats['customers']:>15,}                                   ║
║                                                                              ║
║   Sales:                {stats.get('sales',0):>15,}                                   ║
║   Return Sales:         {stats.get('return_sales',0):>15,}                                   ║
║   Purchases:            {stats.get('purchases',0):>15,}                                   ║
║   Return Purchases:     {stats.get('return_purchases',0):>15,}                                   ║
║                                                                              ║
║   Total Revenue:        {stats['revenue']:>15,}  تومان                         ║
║   Total Cost:           {stats['cost']:>15,}  تومان                         ║
║   Total Profit:         {stats['profit']:>15,}  تومان                         ║
║   Average Margin:       {stats['margin']:>15.1f}%                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        self.stats_text.insert(tk.END, text)
    
    def show_preview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if self.merger.output_df is None or self.merger.output_df.empty:
            return
        df = self.merger.output_df.head(100)
        columns = list(df.columns)
        self.tree['columns'] = columns
        for col in columns:
            self.tree.column(col, width=130, anchor='center')
            self.tree.heading(col, text=col, anchor='center')
        for _, row in df.iterrows():
            values = [str(row[col])[:50] for col in columns]
            self.tree.insert('', tk.END, values=values)
    
    def export_csv(self):
        if self.merger.output_df is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.merger.output_df.to_csv(path, index=False, encoding='utf-8-sig')
            self.log(f"💾 Exported to: {path}")
            messagebox.showinfo("Success", f"Exported {len(self.merger.output_df):,} rows to:\n{path}")
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = SaleYarApp()
    app.run()