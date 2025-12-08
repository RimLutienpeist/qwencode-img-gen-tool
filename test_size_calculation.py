#!/usr/bin/env python3
"""
测试智能尺寸计算函数

运行方式：
    python test_size_calculation.py
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import calculate_api_size

def test_size(target_size, description=""):
    """测试单个尺寸"""
    api_size, scale_factor, need_resize = calculate_api_size(target_size)

    print(f"\n{'='*60}")
    if description:
        print(f"测试: {description}")
    print(f"{'='*60}")
    print(f"目标尺寸:   {target_size}")
    print(f"API 尺寸:   {api_size}")
    print(f"缩放因子:   {scale_factor:.2f}x")
    print(f"需要缩放:   {'是' if need_resize else '否'}")

    if need_resize:
        if scale_factor > 1:
            print(f"处理策略:   生成 {api_size} → 缩小为 {target_size}")
        else:
            print(f"处理策略:   生成 {api_size} → 放大为 {target_size}")
    else:
        print(f"处理策略:   直接使用 {api_size}，无需后处理 ✅")

def main():
    print("\n" + "="*60)
    print("智能尺寸计算函数测试")
    print("="*60)

    # 测试小尺寸
    test_size("64x64", "超小图标")
    test_size("128x128", "小图标")
    test_size("256x256", "UI 图标")

    # 测试标准范围（512-2048）
    test_size("512x512", "标准图标 (范围内)")
    test_size("1024x1024", "标准素材 (范围内)")
    test_size("1920x1080", "横向背景 (范围内)")
    test_size("1080x1920", "纵向背景 (范围内)")
    test_size("2048x2048", "高清素材 (范围内)")

    # 测试大尺寸
    test_size("4096x4096", "4K 素材")
    test_size("3840x2160", "4K 横向背景")
    test_size("8192x8192", "超大素材")

    # 测试非标准尺寸
    test_size("1600x900", "非标准背景")
    test_size("800x600", "非标准尺寸")

    print("\n" + "="*60)
    print("测试完成！")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
