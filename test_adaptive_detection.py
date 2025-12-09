#!/usr/bin/env python3
"""
测试自适应背景检测功能
"""
import numpy as np
import cv2
from PIL import Image as PILImage
import os
import sys

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main

def create_test_image(bg_color, fg_color, size=(512, 512)):
    """
    创建测试图像：纯色背景 + 中央矩形前景

    Args:
        bg_color: 背景色 (B, G, R)
        fg_color: 前景色 (B, G, R)
        size: 图像大小

    Returns:
        numpy array (BGR)
    """
    h, w = size
    img = np.full((h, w, 3), bg_color, dtype=np.uint8)

    # 在中央绘制前景矩形 (20% margin)
    margin_h = h // 5
    margin_w = w // 5
    img[margin_h:-margin_h, margin_w:-margin_w] = fg_color

    return img

def test_detect_background_color():
    """测试背景色检测函数"""
    print("=" * 60)
    print("测试 1: 背景色检测准确性")
    print("=" * 60)

    test_cases = [
        ("白色背景", (255, 255, 255), (0, 0, 255)),      # 白背景 + 红前景
        ("黑色背景", (0, 0, 0), (255, 255, 255)),        # 黑背景 + 白前景
        ("红色背景", (0, 0, 255), (255, 255, 255)),      # 红背景 + 白前景
        ("蓝色背景", (255, 0, 0), (255, 255, 0)),        # 蓝背景 + 黄前景
        ("绿色背景", (0, 255, 0), (255, 0, 255)),        # 绿背景 + 紫前景
        ("灰色背景", (128, 128, 128), (255, 255, 255)),  # 灰背景 + 白前景
    ]

    success_count = 0
    for name, bg_color, fg_color in test_cases:
        img = create_test_image(bg_color, fg_color)
        detected_color, std, is_pure = main.detect_background_color(img, debug=False)

        # 计算颜色差异
        diff = np.abs(detected_color.astype(np.float32) - np.array(bg_color).astype(np.float32))
        max_diff = np.max(diff)

        # 判断是否检测正确（允许 5 个像素值的误差）
        is_correct = max_diff < 5
        success_count += is_correct

        status = "✅" if is_correct else "❌"
        print(f"{status} {name}: 期望 {bg_color}, 检测到 {tuple(detected_color)}")
        print(f"   最大差异: {max_diff:.1f}, 标准差: {std:.1f}, 纯净: {is_pure}")

    print(f"\n测试结果: {success_count}/{len(test_cases)} 通过")
    return success_count == len(test_cases)

def test_is_background_color():
    """测试背景色判断函数"""
    print("\n" + "=" * 60)
    print("测试 2: 背景色像素判断")
    print("=" * 60)

    # 创建白色背景 + 红色前景的测试图像
    img = create_test_image((255, 255, 255), (0, 0, 255))
    bg_color = np.array([255, 255, 255], dtype=np.uint8)

    # 检测背景像素
    is_bg = main.is_background_color(img, bg_color, tolerance=40)

    # 统计背景像素数
    bg_pixels = np.sum(is_bg)
    total_pixels = is_bg.size
    bg_ratio = bg_pixels / total_pixels

    # 理论上背景应该占 64% (边缘 20% margin)
    expected_ratio = 0.64
    is_correct = abs(bg_ratio - expected_ratio) < 0.05

    status = "✅" if is_correct else "❌"
    print(f"{status} 背景像素比例: {bg_ratio:.2%} (期望 {expected_ratio:.0%})")
    print(f"   背景像素: {bg_pixels:,} / {total_pixels:,}")

    return is_correct

def test_end_to_end():
    """端到端测试：生成图像并移除背景"""
    print("\n" + "=" * 60)
    print("测试 3: 端到端自适应背景移除")
    print("=" * 60)

    test_dir = "./test_output"
    os.makedirs(test_dir, exist_ok=True)

    test_cases = [
        ("white_bg", (255, 255, 255), (255, 0, 0)),    # 白背景
        ("blue_bg", (255, 0, 0), (255, 255, 0)),       # 蓝背景
        ("gray_bg", (180, 180, 180), (0, 0, 255)),     # 灰背景
    ]

    success_count = 0
    for name, bg_color, fg_color in test_cases:
        # 创建测试图像
        img = create_test_image(bg_color, fg_color)
        filepath = os.path.join(test_dir, f"test_{name}.png")

        # 保存为 PNG
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = PILImage.fromarray(img_rgb)
        pil_img.save(filepath)

        # 测试自适应背景移除
        success, pixels_removed = main.remove_white_background_grabcut(
            filepath, name,
            skip_backgrounds=False,
            overwrite=True,
            auto_detect=True,
            tolerance=40
        )

        status = "✅" if success else "❌"
        print(f"{status} {name}: 移除 {pixels_removed:,} 像素")

        success_count += success

    print(f"\n测试结果: {success_count}/{len(test_cases)} 通过")
    print(f"测试图像保存在: {os.path.abspath(test_dir)}/")

    return success_count == len(test_cases)

def main_test():
    """运行所有测试"""
    print("🧪 开始测试自适应背景检测功能\n")

    results = []
    results.append(("背景色检测", test_detect_background_color()))
    results.append(("背景像素判断", test_is_background_color()))
    results.append(("端到端测试", test_end_to_end()))

    print("\n" + "=" * 60)
    print("📊 测试总结")
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
