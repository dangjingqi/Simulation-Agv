#!/usr/bin/env python3
import sys
import os
import subprocess

print("=" * 60)
print("Python 环境诊断报告")
print("=" * 60)

# 1. Python 解释器路径
print(f"\n1. Python 解释器: {sys.executable}")

# 2. 判断是否在 venv 中
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    print("   状态: ✅ 正在使用虚拟环境 (venv)")
else:
    print("   状态: ❌ 使用系统 Python 环境")

# 3. 检查 VIRTUAL_ENV 环境变量
venv_path = os.environ.get('VIRTUAL_ENV')
if venv_path:
    print(f"\n2. VIRTUAL_ENV 变量: {venv_path}")
    print("   状态: ✅ 已激活 venv")
else:
    print("\n2. VIRTUAL_ENV 变量: 未设置")
    print("   状态: ❌ 未激活 venv")

# 4. 检查 pip 位置
try:
    pip_path = subprocess.check_output(['which', 'pip'], text=True).strip()
    print(f"\n3. pip 位置: {pip_path}")
    if 'venv' in pip_path:
        print("   状态: ✅ pip 来自 venv")
    else:
        print("   状态: ❌ pip 来自系统")
except:
    print("\n3. pip 位置: 未找到")

# 5. 检查 requests 库
try:
    import requests
    print(f"\n4. requests 库: ✅ 已安装")
    print(f"   位置: {requests.__file__}")
except ImportError:
    print("\n4. requests 库: ❌ 未安装")
    print("   运行: pip install requests")

print("\n" + "=" * 60)