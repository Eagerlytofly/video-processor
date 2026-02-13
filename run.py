#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
视频处理系统启动脚本
"""

import sys
import os

# 添加app目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# 导入并运行主程序
from main import main

if __name__ == "__main__":
    main()
