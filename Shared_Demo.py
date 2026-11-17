"""Entrypoint for an isolated, synthetic-only shared demonstration."""

import os
import runpy
import sys

os.environ["SCHOOLFLOW_SHARED_DEMO"] = "1"
app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SchoolFlow_AI_MVP")
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
runpy.run_path(os.path.join(app_dir, "app.py"), run_name="__main__")
