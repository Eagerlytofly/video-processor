"""pytest 配置：将 app 加入路径以便导入 core/config/utils。"""
import os
import sys

root = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(root, "..", "app")
app_dir = os.path.abspath(app_dir)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
