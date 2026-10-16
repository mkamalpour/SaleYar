"""
run.py

Interactive command launcher for SaleYar.
Use this script to generate sample data, train models, launch the owner HTML dashboard,
launch the developer UI, launch terminal mode, or get API instructions.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import console  # noqa: F401  — forces UTF-8 stdout before anything prints

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def run_subprocess(command: list[str], cwd: str = PROJECT_ROOT) -> int:
    print(f"Running: {' '.join(command)}")
    result = subprocess.run([sys.executable] + command, cwd=cwd)
    if result.returncode != 0:
        print(f"Command failed with code {result.returncode}")
    return result.returncode


def run_html_dashboard() -> None:
    """Launch the owner dashboard and the API server."""
    import socketserver
    import threading
    import time
    import webbrowser

    api_port = int(os.environ.get("SALEYAR_API_PORT", "8000"))
    web_port = int(os.environ.get("SALEYAR_WEB_PORT", "3000"))
    html_path = os.path.join(PROJECT_ROOT, "ui", "owner.html")

    if not os.path.exists(html_path):
        print(f"ERROR: {html_path} not found.")
        return

    import config

    injected_key = config.API_KEY
    dashboard_url = f"http://localhost:{web_port}/ui/owner.html"

    from ui.server import create_dashboard_handler
    DashboardHandler = create_dashboard_handler(PROJECT_ROOT, injected_key, api_port)

    # Start API server in a background thread.
    def start_api():
        import uvicorn
        uvicorn.run("api.main:app", host="127.0.0.1", port=api_port, log_level="warning")

    def start_web():
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.ThreadingTCPServer(("127.0.0.1", web_port), DashboardHandler) as httpd:
            httpd.serve_forever()

    for thread, name in ((start_api, "api"), (start_web, "web")):
        threading.Thread(target=thread, name=f"saleyar-{name}", daemon=True).start()

    # Wait for both ports to accept connections instead of sleeping blindly.
    def wait_for_port(port: int, timeout: float = 30.0) -> bool:
        import socket
        deadline = time.time() + timeout
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return True
            time.sleep(0.3)
        return False

    if not wait_for_port(api_port):
        print(f"ERROR: API did not come up on port {api_port}.")
        return
    if not wait_for_port(web_port):
        print(f"ERROR: dashboard did not come up on port {web_port}.")
        return

    webbrowser.open(dashboard_url)

    print("\n" + "=" * 58)
    print("  SaleYar is running")
    print("=" * 58)
    print(f"  Dashboard : {dashboard_url}")
    print(f"  API       : http://127.0.0.1:{api_port}")
    print("  API key   : configured automatically in the local dashboard")
    print("\n  Press Ctrl+C to stop.")
    print("=" * 58 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nGoodbye!")


def run_developer_ui() -> None:
    from ui import run_developer
    run_developer()


def run_terminal_mode() -> None:
    """Run the terminal-based version (no browser needed)."""
    ensure_sample_data()
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


SAMPLE_CSV = os.path.join("data", "sample_en.csv")


def ensure_sample_data() -> bool:
    """Generate the sample CSV on first run if it is missing.

    The generated samples are git-ignored (they are ~13 MB and fully
    reproducible from data/generate_data.py), so a fresh clone has to create
    them before the terminal UI, demo training or the test suite can run.
    """
    target = os.path.join(PROJECT_ROOT, SAMPLE_CSV)
    if os.path.exists(target) and os.path.getsize(target) > 0:
        return True

    print("Sample data not found — generating it now (one time, ~30s)...")
    code = run_subprocess(
        [os.path.join("data", "generate_data.py"), "--invoices", "15000",
         "--customers", "500", "--seed", "42"]
    )
    if code != 0 or not os.path.exists(target):
        print("Could not generate sample data. Run: python data/generate_data.py")
        return False
    return True


def generate_sample_data() -> None:
    if run_subprocess(["data/generate_data.py"]):
        print("Sample data generation failed.")
    else:
        print("Sample data generated in data/sample_en.csv and data/sample_fa.csv.")


def train_demo_models() -> None:
    if not ensure_sample_data():
        return
    print("Training demo models with data/sample_en.csv...")
    if run_subprocess(["models/train.py", "--shop_id", "demo", "--csv", SAMPLE_CSV]):
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