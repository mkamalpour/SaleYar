import subprocess
import sys

packages = [
    "pandas", "numpy", "sklearn", "lightgbm", "openpyxl",
    "plotly", "scipy", "statsforecast", "mlxtend", "ortools",
    "fastapi", "uvicorn", "gradio", "jdatetime", "persiantools",
    "rapidfuzz", "python-dotenv", "joblib", "rich", "threadpoolctl"
]

print("\n" + "="*60)
print("INSTALLED PACKAGES IN saleYar ENVIRONMENT")
print("="*60)
print(f"{'Package':<20} {'Version':<15}")
print("="*60)

for pkg in packages:
    try:
        if pkg == "sklearn":
            version = subprocess.check_output(
                [sys.executable, "-c", "import sklearn; print(sklearn.__version__)"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        elif pkg == "python-dotenv":
            version = subprocess.check_output(
                [sys.executable, "-c", "import dotenv; print(dotenv.__version__)"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        elif pkg == "jdatetime":
            version = subprocess.check_output(
                [sys.executable, "-c", "import jdatetime; print(jdatetime.__version__ if hasattr(jdatetime, '__version__') else 'N/A')"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        elif pkg == "rich":
            version = subprocess.check_output(
                [sys.executable, "-c", "import rich; print(rich.__version__ if hasattr(rich, '__version__') else 'N/A')"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        else:
            version = subprocess.check_output(
                [sys.executable, "-c", f"import {pkg}; print({pkg}.__version__)"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        
        print(f"{pkg:<20} {version:<15}")
    except:
        print(f"{pkg:<20} NOT INSTALLED")

print("="*60)


"""
INSTALLED PACKAGES IN saleYar ENVIRONMENT on my pc
============================================================
Package              Version        
============================================================
pandas               2.3.3          
numpy                1.26.4         
sklearn              1.7.2          
lightgbm             4.6.0          
openpyxl             3.1.5          
plotly               6.6.0          
scipy                1.15.2         
statsforecast        2.0.3          
mlxtend              0.23.4         
ortools              9.14.6206      
fastapi              0.133.1        
uvicorn              0.41.0         
gradio               6.14.0         
jdatetime            N/A            
persiantools         5.5.0          
rapidfuzz            3.14.3         
python-dotenv        NOT INSTALLED
joblib               1.5.3          
rich                 N/A            
threadpoolctl        3.6.0          
============================================================
"""