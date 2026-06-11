"""
ui/terminal.py

Terminal-based interface for SaleYar.
Smart behavior:
  - Press Enter → uses default path (data/sample_en.csv)
  - Type a path → uses that path
  - Type 0 → returns to run.py menu
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ═══════════════════════════════════════════════════════════════════
# 🔧 HARDCODED DEFAULT PATH (used when user presses Enter)
# ═══════════════════════════════════════════════════════════════════
DEFAULT_CSV_PATH = "data/sample_en.csv"

# Default settings
DEFAULT_BUDGET = 100_000_000
DEFAULT_GOAL = "maximize_profit"
DEFAULT_LANGUAGE = "en"
# ═══════════════════════════════════════════════════════════════════

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from models import loader
from output import reporter
from pipeline import runner

console = Console()
BACK_TO_MENU = False


def print_header():
    """Print beautiful header"""
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]🏪 SALEYAR[/] — Terminal Mode\n"
        "[dim]Press [bold]Enter[/] for default file | Type [bold]0[/] to go back[/]",
        border_style="cyan"
    ))


def print_health_score(report: dict):
    """Display health score with color"""
    health = report.get('health_score', 0)
    quality = report.get('data_quality', 0)
    
    if health >= 70:
        color = "green"
        icon = "🟢"
        status = "HEALTHY"
    elif health >= 40:
        color = "yellow"
        icon = "🟡"
        status = "CAUTION"
    else:
        color = "red"
        icon = "🔴"
        status = "CRITICAL"
    
    panel = Panel(
        f"[bold {color}]{icon} HEALTH SCORE: {health}/100 — {status}[/]\n"
        f"📊 Data Quality: {quality}/100",
        title="🏥 SHOP HEALTH",
        border_style=color,
        box=box.ROUNDED
    )
    console.print(panel)


def print_top_actions(report: dict):
    """Display priority actions"""
    actions = report.get('priority_actions', [])
    if not actions:
        console.print("[dim]No priority actions generated.[/]")
        return
    
    console.print("\n[bold yellow]🚨 TOP ACTIONS[/]\n")
    
    for i, action in enumerate(actions[:3], 1):
        urgency = action.get('urgency', 'normal')
        if urgency == 'urgent':
            icon = "🔥"
            color = "red"
        else:
            icon = "📌"
            color = "white"
        
        console.print(f"  [bold {color}]{i}. {icon} {action.get('title', 'Action')}[/]")
        console.print(f"     [dim]{action.get('description', '')}[/]\n")


def print_roi_commentary(report: dict):
    """Display ROI comparison"""
    roi_text = report.get('roi_commentary', '')
    if roi_text:
        console.print(Panel(roi_text, title="💰 PROFIT ANALYSIS", border_style="green", box=box.ROUNDED))


def print_products_table(report: dict):
    """Display products with risk scores"""
    products = report.get('products', [])
    if not products:
        console.print("[dim]No products analyzed.[/]")
        return
    
    table = Table(title="📦 PRODUCT ANALYSIS", box=box.ROUNDED, border_style="cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Product", style="cyan", no_wrap=True)
    table.add_column("Margin", justify="right")
    table.add_column("Risk", justify="right")
    table.add_column("Segment", style="magenta")
    table.add_column("Action", style="green")
    
    for idx, p in enumerate(products[:30], 1):
        margin = p.get('profit_margin', 0)
        risk = p.get('risk_score', 50)
        segment = p.get('segment', '?')
        
        if risk < 30:
            risk_color = "green"
            risk_icon = "🟢"
            action = "✅ BUY"
        elif risk < 70:
            risk_color = "yellow"
            risk_icon = "🟡"
            action = "⚠️ CAUTION"
        else:
            risk_color = "red"
            risk_icon = "🔴"
            action = "❌ AVOID"
        
        segment_icons = {
            "Star": "⭐", "Reliable": "🤝", "Seasonal": "📅",
            "Deadweight": "⚰️", "Risky": "💣", "Outlier": "🔄"
        }
        segment_icon = segment_icons.get(segment, "📦")
        
        table.add_row(
            str(idx),
            p.get('product', '?')[:30],
            f"{margin:.1f}%",
            f"[{risk_color}]{risk_icon} {risk:.0f}[/]",
            f"{segment_icon} {segment}",
            action
        )
    
    console.print(table)


def print_order_summary(report: dict, budget: float):
    """Display purchase order recommendation"""
    order = report.get('purchase_order', [])
    budget_used = report.get('order_total', 0)
    
    if not order:
        console.print("[dim]No order recommendation generated.[/]")
        return
    
    budget_pct = (budget_used / budget * 100) if budget > 0 else 0
    bar_length = 30
    filled = int(bar_length * budget_pct / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    console.print(f"\n💰 [bold]Budget: {budget:,.0f} IRR[/]")
    console.print(f"   [dim]Used: {budget_used:,.0f} IRR ({budget_pct:.1f}%)[/]")
    console.print(f"   [{'green' if budget_pct <= 100 else 'red'}]{bar}[/]")
    
    table = Table(title="💼 PURCHASE ORDER", box=box.ROUNDED, border_style="green")
    table.add_column("Product", style="cyan", no_wrap=True)
    table.add_column("Units", justify="right")
    table.add_column("Unit Cost", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Why", style="dim")
    
    for item in order[:20]:
        qty = item.get('qty', 0)
        if qty > 0:
            table.add_row(
                item.get('product', '?')[:25],
                f"{qty:.0f}",
                f"{item.get('unit_cost', 0):,.0f}",
                f"{item.get('total_cost', 0):,.0f}",
                item.get('reason', '?')[:35]
            )
    
    if table.row_count > 0:
        console.print(table)


def print_segments_summary(report: dict):
    """Display segment breakdown"""
    segments = report.get('segment_summary', {})
    if not segments:
        return
    
    segment_info = {
        "Star": ("⭐", "green", "Best sellers — keep stocked"),
        "Reliable": ("🤝", "cyan", "Steady income — maintain stock"),
        "Seasonal": ("📅", "yellow", "Seasonal peaks — plan ahead"),
        "Deadweight": ("⚰️", "red", "Slow sellers — reduce or remove"),
        "Risky": ("💣", "orange1", "High volatility — be careful"),
        "Outlier": ("🔄", "magenta", "Unusual — check manually")
    }
    
    console.print("\n[bold]📊 PRODUCT SEGMENTS[/]\n")
    for seg, count in segments.items():
        icon, color, desc = segment_info.get(seg, ("📦", "white", ""))
        console.print(f"  {icon} [bold {color}]{seg}:[/] {count} products — [dim]{desc}[/]")


def print_customers_summary(report: dict):
    """Display customer segments"""
    customers = report.get('customers', {})
    if customers.get('skipped'):
        console.print("[dim]Customer analysis skipped (not enough data)[/]")
        return
    
    summary = customers.get('summary', {})
    if not summary:
        return
    
    console.print("\n[bold]👥 CUSTOMER SEGMENTS[/]\n")
    
    segment_icons = {
        "Champions": "🏆", "Loyal": "🤝",
        "At-Risk": "⚠️", "Lost": "💔"
    }
    
    for seg, count in summary.items():
        icon = segment_icons.get(seg, "👤")
        console.print(f"  {icon} [bold]{seg}:[/] {count} customers")


def print_basket_rules(report: dict):
    """Display top basket rules"""
    rules = report.get('basket_rules', [])
    if not rules:
        console.print("[dim]Not enough data for basket analysis[/]")
        return
    
    table = Table(title="🛒 BASKET RULES", box=box.SIMPLE, border_style="magenta")
    table.add_column("If Customer Buys", style="cyan")
    table.add_column("Also Buys", style="green")
    table.add_column("Confidence", justify="right")
    
    for rule in rules[:10]:
        antecedent = " + ".join(rule.get('antecedent', []))[:25]
        consequent = " + ".join(rule.get('consequent', []))[:25]
        confidence = f"{rule.get('confidence', 0) * 100:.0f}%"
        table.add_row(antecedent, consequent, confidence)
    
    if table.row_count > 0:
        console.print(table)


def print_forecast_highlights(report: dict):
    """Display forecast highlights"""
    products = report.get('products', [])
    forecast_items = []
    
    for p in products:
        fc = p.get('forecast', {})
        if fc and not fc.get('skipped'):
            forecast_items.append({
                'product': p['product'],
                'h30': fc.get('h30', 0)
            })
    
    if not forecast_items:
        console.print("[dim]Not enough history for forecast[/]")
        return
    
    forecast_items.sort(key=lambda x: x['h30'], reverse=True)
    
    console.print("\n[bold]📈 TOP 5 FORECASTED PRODUCTS (Next 30 days)[/]\n")
    for i, item in enumerate(forecast_items[:5], 1):
        console.print(f"  {i}. [cyan]{item['product']}[/] → [green]{item['h30']:.0f} units[/]")


def print_footer():
    """Print completion footer"""
    console.print("\n" + "=" * 70)
    console.print("[bold green]✅ ANALYSIS COMPLETE[/]")
    console.print("=" * 70 + "\n")


def run_terminal():
    """Main entry point — smart terminal with back-to-menu option"""
    global BACK_TO_MENU
    BACK_TO_MENU = False
    
    print_header()
    
    # ─────────────────────────────────────────────────────────────
    # Get CSV file path with smart default
    # ─────────────────────────────────────────────────────────────
    console.print(f"\n📁 [bold]CSV File Path[/]")
    console.print(f"   [dim](Press Enter for default: {DEFAULT_CSV_PATH})[/]")
    console.print(f"   [dim](Type 0 to go back to menu)[/]")
    
    user_input = input("\n👉 Path: ").strip()
    
    if user_input == "0":
        console.print("\n[dim]↩️  Returning to main menu...[/]")
        return  # This goes back to run.py
    
    csv_path = user_input if user_input else DEFAULT_CSV_PATH
    
    if not os.path.exists(csv_path):
        console.print(f"\n[red]❌ ERROR: File not found: {csv_path}[/]")
        console.print("\n[dim]Press Enter to try again...[/]")
        input()
        run_terminal()  # Restart terminal
        return
    
    # ─────────────────────────────────────────────────────────────
    # Get budget (optional)
    # ─────────────────────────────────────────────────────────────
    console.print(f"\n💰 [bold]Budget (IRR)[/]")
    console.print(f"   [dim](Press Enter for default: {DEFAULT_BUDGET:,})[/]")
    
    budget_input = input("👉 Budget: ").strip()
    if budget_input == "0":
        run_terminal()
        return
    
    budget = float(budget_input) if budget_input else DEFAULT_BUDGET
    
    # ─────────────────────────────────────────────────────────────
    # Get goal (optional)
    # ─────────────────────────────────────────────────────────────
    console.print(f"\n🎯 [bold]Optimization Goal[/]")
    console.print(f"   1. maximize_profit [dim](default)[/]")
    console.print(f"   2. cover_customers")
    console.print(f"   3. reduce_risk")
    
    goal_input = input("👉 Goal (1-3) or Enter: ").strip()
    if goal_input == "0":
        run_terminal()
        return
    
    goal_map = {
        "1": "maximize_profit",
        "2": "cover_customers",
        "3": "reduce_risk"
    }
    goal = goal_map.get(goal_input, DEFAULT_GOAL)
    
    # ─────────────────────────────────────────────────────────────
    # Get language (optional)
    # ─────────────────────────────────────────────────────────────
    console.print(f"\n🌐 [bold]Language[/]")
    console.print(f"   1. English [dim](default)[/]")
    console.print(f"   2. فارسی")
    
    lang_input = input("👉 Language (1-2) or Enter: ").strip()
    if lang_input == "0":
        run_terminal()
        return
    
    language = "fa" if lang_input == "2" else DEFAULT_LANGUAGE
    
    # ─────────────────────────────────────────────────────────────
    # Shop ID (optional)
    # ─────────────────────────────────────────────────────────────
    console.print(f"\n🏷️  [bold]Shop ID[/]")
    console.print(f"   [dim](Press Enter for: terminal_shop)[/]")
    
    shop_id_input = input("👉 Shop ID: ").strip()
    if shop_id_input == "0":
        run_terminal()
        return
    
    shop_id = shop_id_input if shop_id_input else "terminal_shop"
    
    # ─────────────────────────────────────────────────────────────
    # Show summary and confirm
    # ─────────────────────────────────────────────────────────────
    console.print("\n" + "─" * 50)
    console.print("[bold cyan]📋 Summary[/]")
    console.print(f"   File:   {csv_path}")
    console.print(f"   Budget: {budget:,.0f} IRR")
    console.print(f"   Goal:   {goal}")
    console.print(f"   Lang:   {language}")
    console.print(f"   Shop:   {shop_id}")
    console.print("─" * 50)
    
    confirm = input("\n🚀 Run analysis? (Enter = Yes, 0 = No): ").strip()
    if confirm == "0":
        run_terminal()
        return
    
    # ─────────────────────────────────────────────────────────────
    # Run the pipeline
    # ─────────────────────────────────────────────────────────────
    console.print("\n[bold cyan]🔄 Loading models...[/]")
    loader.load_all()
    
    console.print("\n[bold cyan]🚀 Running full pipeline...[/]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing data...", total=None)
        
        with open(csv_path, "rb") as f:
            file_bytes = f.read()
        
        filename = os.path.basename(csv_path)
        result = runner.run_pipeline(
            file_bytes, filename, budget, shop_id, goal, language
        )
        
        progress.update(task, completed=True)
    
    if not result.get("passed"):
        console.print(f"\n[red]❌ Pipeline failed: {result.get('stop_reason', 'Unknown error')}[/]")
        console.print("\n[dim]Press Enter to continue...[/]")
        input()
        run_terminal()
        return
    
    # Assemble and display report
    report = reporter.assemble_and_save(result, shop_id)
    
    print_health_score(report)
    print_roi_commentary(report)
    print_top_actions(report)
    print_forecast_highlights(report)
    print_segments_summary(report)
    print_order_summary(report, budget)
    print_products_table(report)
    print_basket_rules(report)
    print_customers_summary(report)
    print_footer()
    
    json_path = f"saved_reports/{shop_id}/report_latest.json"
    console.print(f"[dim]📄 Full JSON report saved to: {json_path}[/]")
    
    console.print("\n[dim]Press Enter to continue or 0 to go back to menu...[/]")
    if input().strip() == "0":
        run_terminal()
        return


if __name__ == "__main__":
    run_terminal()