"""
cpi_benchmark.py — Benchmark APIx monthly index against official MoSPI CPI airfare index.
Proxies to Airiva.backtest.cpi_benchmark.
"""
from Airiva.backtest.cpi_benchmark import *

if __name__ == "__main__":
    import sys
    from Airiva.backtest.cpi_benchmark import __name__ as _name
    import runpy
    runpy.run_module("Airiva.backtest.cpi_benchmark", run_name="__main__")
