"""
run.py

Interactive command launcher for SaleYar.
Use this script to generate sample data, train models, launch the owner HTML dashboard,
launch the developer UI, launch terminal mode, or get API instructions.
"""

import argparse
import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def run_subprocess(command: list[str], cwd: str = PROJECT_ROOT) -> int:
    print(f"Running: {' '.join(command)}")
    result = subprocess.run([sys.executable] + command, cwd=cwd)
    if result.returncode != 0:
        print(f"Command failed with code {result.returncode}")
    return result.returncode


def clear_shop_models() -> None:
    """Delete all per-shop model folders so every run starts fresh."""
    shops_dir = os.path.join(PROJECT_ROOT, "models", "shops")
    if os.path.exists(shops_dir):
        for item in os.listdir(shops_dir):
            path = os.path.join(shops_dir, item)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                print(f"Warning: could not remove {path}: {e}")
    else:
        os.makedirs(shops_dir, exist_ok=True)


def run_html_dashboard() -> None:
    """Launch the professional HTML dashboard and API server."""
    import webbrowser
    import threading
    import time
    import subprocess
    import sys
    import os
    
    # Start API server in background
    def start_api():
        subprocess.run([
            sys.executable, "-m", "uvicorn", "api.main:app",
            "--host", "0.0.0.0", "--port", "8000"
        ])
    
    # Start HTTP server to serve the HTML file
    def start_html():
        import http.server
        import socketserver
        
        PORT = 3000
        os.chdir(PROJECT_ROOT)
        
        # Ensure the HTML exists at ui/site.html
        html_path = os.path.join(PROJECT_ROOT, "ui", "owner.html")
        if not os.path.exists(html_path):
            print(f"❌ ERROR: {html_path} not found. Save your HTML dashboard as ui/owner.html")
            return
        
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", PORT), handler) as httpd:
            print(f"🌐 HTML Dashboard running at http://localhost:{PORT}/ui/owner.html")
            httpd.serve_forever()
    
    # Start API in background thread
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    
    # Wait for API to start
    time.sleep(3)
    
    # Start HTML server
    html_thread = threading.Thread(target=start_html, daemon=True)
    html_thread.start()
    
    time.sleep(2)
    
    # Open browser
    webbrowser.open("http://localhost:3000/ui/owner.html")
    
    print("\n✅ SaleYar fully started!")
    print("   - API running on port 8000")
    print("   - Dashboard on port 3000")
    print("   Press Ctrl+C to stop everything.\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


def run_developer_ui() -> None:
    from ui import run_developer
    run_developer()


def run_terminal_mode() -> None:
    """Run the terminal-based version (no browser needed)."""
    from ui import run_terminal
    run_terminal()


def show_api_instructions() -> None:
    """Display all API endpoints with examples in a friendly format."""
    print("\n" + "▰" * 70)
    print("  🚀 SALEYAR API — Complete Reference")
    print("▰" * 70)
    print("\n📍 Base URL:  http://localhost:8000")
    print("🔐 Auth:      Header 'X-API-Key: your-key' (required for all endpoints)")
    print("📄 Docs:      http://localhost:8000/docs (if online)")
    print("\n" + "─" * 70)
    print("📤 1. FULL ANALYSIS (Async — runs in background)")
    print("─" * 70)
    print("POST /analyze")
    print("     Upload CSV → get job_id → poll /result/{job_id}")
    print()
    print("     curl -X POST -H 'X-API-Key: your-key' \\")
    print("          -F 'file=@sales.csv' \\")
    print("          -F 'shop_id=demo' \\")
    print("          -F 'budget=10000000' \\")
    print("          -F 'goal=maximize_profit' \\")
    print("          -F 'language=en' \\")
    print("          http://localhost:8000/analyze")
    print("\n" + "─" * 70)
    print("🔍 2. CHECK JOB STATUS")
    print("─" * 70)
    print("GET /result/{job_id}")
    print("     Poll every 3 seconds until status='done'")
    print()
    print("     curl -H 'X-API-Key: your-key' \\")
    print("          http://localhost:8000/result/abc-123-def")
    print("\n" + "─" * 70)
    print("⚡ 3. QUICK ENDPOINTS (No full pipeline — instant results)")
    print("─" * 70)
    print("\n  📦 OPTIMIZER — What to buy for a given budget")
    print("  POST /optimize")
    print("      curl -X POST -H 'X-API-Key: your-key' \\")
    print("           -H 'Content-Type: application/json' \\")
    print("           -d '{\"shop_id\":\"demo\",\"budget\":5000000,\"goal\":\"profit\"}' \\")
    print("           http://localhost:8000/optimize")
    print("\n  🛒 BASKET — Which products are bought together")
    print("  POST /basket")
    print("      curl -X POST -H 'X-API-Key: your-key' \\")
    print("           -F 'file=@sales.csv' \\")
    print("           -F 'shop_id=demo' \\")
    print("           http://localhost:8000/basket")
    print("\n  🎯 RISK — Risk score for each product")
    print("  POST /risk")
    print("      curl -X POST -H 'X-API-Key: your-key' \\")
    print("           -F 'file=@sales.csv' \\")
    print("           -F 'language=en' \\")
    print("           http://localhost:8000/risk")
    print("\n" + "─" * 70)
    print("📊 4. SAVED REPORTS (Instant — no processing)")
    print("─" * 70)
    print("\n  📄 Full report")
    print("  GET /report/{shop_id}")
    print("      curl -H 'X-API-Key: your-key' \\")
    print("           http://localhost:8000/report/demo")
    print("\n  ❤️ Health score only")
    print("  GET /health/{shop_id}")
    print("      curl -H 'X-API-Key: your-key' \\")
    print("           http://localhost:8000/health/demo")
    print("\n" + "─" * 70)
    print("🏥 5. SERVER STATUS")
    print("─" * 70)
    print("GET /healthcheck")
    print("     Check if server is alive, models loaded, uptime")
    print()
    print("     curl -H 'X-API-Key: your-key' \\")
    print("          http://localhost:8000/healthcheck")
    print("\n" + "▰" * 70)
    print("  🚀 START THE API SERVER")
    print("▰" * 70)
    print()
    print("  uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2")
    print()
    print("  💡 Pro tip: Use --reload for development")
    print("     uvicorn api.main:app --reload --port 8000")
    print()
    print("▰" * 70)


def generate_sample_data() -> None:
    if run_subprocess(["data/generate_data.py"]):
        print("Sample data generation failed.")
    else:
        print("Sample data generated in data/sample_en.csv and data/sample_fa.csv.")


def train_demo_models() -> None:
    print("Training demo models with data/sample_en.csv...")
    if run_subprocess(["models/train.py", "--shop_id", "demo", "--csv", "data/sample_en.csv"]):
        print("Demo model training failed.")
    else:
        print("Demo models trained and saved in models/.")


def show_menu() -> None:
    print("\n" + "=" * 50)
    print("  SaleYar Command Menu")
    print("=" * 50)
    print("1) 🏪  Shop owner dashboard (HTML – recommended)")
    print("2) 🔧 Developer UI (Gradio – for debugging)")
    print("3) 💻 Terminal mode (no browser needed)")
    print("4) 📊 Generate sample data")
    print("5) 🤖 Train demo models")
    print("6) 🔌 Show API endpoints & instructions")
    print("7) ❌ Quit")
    print("=" * 50)


def prompt_choice() -> str:
    return input("Choose an option [1-7]: ").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="SaleYar project launcher")
    parser.add_argument("--mode", choices=["owner", "developer", "terminal", "api"], 
                        help="Launch a specific mode directly.")
    parser.add_argument("--generate-data", action="store_true", help="Generate sample data.")
    parser.add_argument("--train-demo", action="store_true", help="Train demo models using sample data.")
    args = parser.parse_args()

    clear_shop_models()

    if args.generate_data:
        generate_sample_data()
        return
    if args.train_demo:
        train_demo_models()
        return
    if args.mode:
        if args.mode == "owner":
            run_html_dashboard()
        elif args.mode == "developer":
            run_developer_ui()
        elif args.mode == "terminal":
            run_terminal_mode()
        elif args.mode == "api":
            show_api_instructions()
        return

    while True:
        show_menu()
        choice = prompt_choice()

        if choice == "1":
            run_html_dashboard()
            break
        elif choice == "2":
            run_developer_ui()
            break
        elif choice == "3":
            run_terminal_mode()
            break
        elif choice == "4":
            generate_sample_data()
        elif choice == "5":
            train_demo_models()
        elif choice == "6":
            show_api_instructions()
        elif choice == "7":
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter a number between 1 and 7.")


if __name__ == "__main__":
    main()