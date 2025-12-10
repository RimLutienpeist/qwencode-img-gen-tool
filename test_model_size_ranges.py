#!/usr/bin/env python3
"""
测试模型尺寸自动适配功能
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main

def test_model_size_calculation():
    """测试不同模型的尺寸计算"""
    print("=" * 60)
    print("测试模型尺寸自动适配功能")
    print("=" * 60)

    test_cases = [
        # (模型名, 目标尺寸, 期望API尺寸, 是否需要缩放)
        # V3 模型测试 (512-2048)
        ("doubao-seedream-3-0-t2i-250415", "256x256", "512x512", True),
        ("doubao-seedream-3-0-t2i-250415", "512x512", "512x512", False),
        ("doubao-seedream-3-0-t2i-250415", "1024x1024", "1024x1024", False),
        ("doubao-seedream-3-0-t2i-250415", "2048x2048", "2048x2048", False),
        ("doubao-seedream-3-0-t2i-250415", "4096x4096", "2048x2048", True),

        # V4 模型测试 (1280x720 - 4096x4096)
        ("doubao-seedream-4-0-250828", "512x512", "2048x2048", True),  # 512放大4倍到2048
        ("doubao-seedream-4-0-250828", "1280x720", "1280x720", False),
        ("doubao-seedream-4-0-250828", "1920x1080", "1920x1080", False),
        ("doubao-seedream-4-0-250828", "4096x4096", "4096x4096", False),

        # V4.5 模型测试 (2560x1440 - 4096x4096)
        ("doubao-seedream-4-5-251128", "1024x1024", "4096x4096", True),  # 1024放大4倍到4096
        ("doubao-seedream-4-5-251128", "2560x1440", "2560x1440", False),
        ("doubao-seedream-4-5-251128", "3840x2160", "3840x2160", False),
        ("doubao-seedream-4-5-251128", "4096x4096", "4096x4096", False),
    ]

    success_count = 0
    fail_count = 0

    for model_name, target_size, expected_api_size, expected_resize in test_cases:
        api_size, scale_factor, need_resize = main.calculate_api_size(target_size, model_name)

        # 检查结果
        is_correct = (api_size == expected_api_size and need_resize == expected_resize)

        if is_correct:
            success_count += 1
            status = "✅"
        else:
            fail_count += 1
            status = "❌"

        # 获取模型简称
        model_version = "V3" if "3-0" in model_name else ("V4" if "4-0" in model_name else "V4.5")

        print(f"{status} [{model_version}] {target_size}")
        print(f"   API尺寸: {api_size} (期望: {expected_api_size})")
        print(f"   需要缩放: {need_resize} (期望: {expected_resize})")
        print(f"   缩放因子: {scale_factor:.2f}x")

        if not is_correct:
            print(f"   ⚠️  测试失败！")
        print()

    print("=" * 60)
    print(f"📊 测试结果: {success_count}/{len(test_cases)} 通过")
    print("=" * 60)

    return success_count == len(test_cases)

def test_model_config():
    """测试模型配置是否正确加载"""
    print("\n" + "=" * 60)
    print("测试模型配置")
    print("=" * 60)

    print(f"默认模型: {main.MODEL_NAME}")
    print(f"\n已配置的模型:")

    for model_name, config in main.MODEL_SIZE_RANGES.items():
        print(f"\n📦 {model_name}")
        print(f"   描述: {config['description']}")
        print(f"   最小尺寸: {config['min_width']}x{config['min_height']}")
        print(f"   最大尺寸: {config['max_width']}x{config['max_height']}")

    return True

def main_test():
    """运行所有测试"""
    print("🧪 开始测试模型尺寸自动适配功能\n")

    results = []
    results.append(("模型配置加载", test_model_config()))
    results.append(("尺寸自动适配", test_model_size_calculation()))

    print("\n" + "=" * 60)
    print("📊 总测试结果")
    print("=" * 60)

    passed = sum(r[1] for r in results)
    total = len(results)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status}: {name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    return passed == total

if __name__ == "__main__":
    success = main_test()
    sys.exit(0 if success else 1)
