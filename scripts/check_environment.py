"""Print installed distribution versions without importing ML frameworks."""
from importlib.metadata import PackageNotFoundError, version

PACKAGES = ["pandas", "numpy", "scikit-learn", "lightgbm", "statsforecast", "ortools", "fastapi", "gradio", "python-multipart", "jdatetime"]

def main():
    missing = []
    for package in PACKAGES:
        try:
            print(f"{package:<22} {version(package)}")
        except PackageNotFoundError:
            print(f"{package:<22} missing")
            missing.append(package)
    return bool(missing)

if __name__ == "__main__":
    raise SystemExit(main())
