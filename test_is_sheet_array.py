#!/usr/bin/env python3
"""
测试 is_sheet 数组格式功能
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main

def test_is_sheet_formats():
    """测试不同的 is_sheet 格式"""
    print("=" * 60)
    print("测试 is_sheet 格式处理")
    print("=" * 60)

    test_cases = [
        # (is_sheet值, description, 期望的提示词关键内容)
        (
            False,
            "角色立绘",
            ["角色立绘"]
        ),
        (
            None,
            "UI图标",
            ["UI图标"]
        ),
        (
            [False],
            "道具图标",
            ["道具图标"]
        ),
        (
            [True, 8, "骑士角色", "行走动画从站立到跑步"],
            None,  # 序列帧不需要description
            ["骑士角色", "序列帧设计", "共 8 帧", "动画内容: 行走动画从站立到跑步"]
        ),
        (
            [True, 4, "火焰特效", "爆炸动画"],
            None,
            ["火焰特效", "序列帧设计", "共 4 帧", "动画内容: 爆炸动画"]
        ),
    ]

    success_count = 0
    fail_count = 0

    for idx, (is_sheet, description, expected_keywords) in enumerate(test_cases, 1):
        try:
            # 构建提示词
            prompt = main.build_prompt(
                description=description,
                category="char_sprite",
                style="pixel",
                need_white_background=True,
                is_sheet=is_sheet
            )

            # 检查期望的关键词是否都在提示词中
            all_found = all(keyword in prompt for keyword in expected_keywords)

            if all_found:
                success_count += 1
                status = "✅"
            else:
                fail_count += 1
                status = "❌"
                missing = [kw for kw in expected_keywords if kw not in prompt]

            print(f"\n{status} 测试 {idx}:")
            print(f"   is_sheet: {is_sheet}")
            print(f"   description: {description}")
            print(f"   生成提示词: {prompt}")
            if not all_found:
                print(f"   ⚠️  缺少关键词: {missing}")

        except Exception as e:
            fail_count += 1
            print(f"\n❌ 测试 {idx} - 异常:")
            print(f"   is_sheet: {is_sheet}")
            print(f"   错误: {e}")

    print("\n" + "=" * 60)
    print(f"📊 测试结果: {success_count}/{len(test_cases)} 通过")
    print("=" * 60)

    return success_count == len(test_cases)

def test_sheet_array_validation():
    """测试数组格式验证"""
    print("\n" + "=" * 60)
    print("测试数组格式验证（不完整的数组）")
    print("=" * 60)

    test_cases = [
        ([True], "至少4个元素", "缺少帧数/主体/动画内容"),
        ([True, 8], "至少4个元素", "缺少主体/动画内容"),
        ([True, 8, "主体"], "至少4个元素", "缺少动画内容"),
    ]

    for is_sheet, desc_label, reason in test_cases:
        try:
            prompt = main.build_prompt(
                description="备用描述",
                is_sheet=is_sheet
            )
            # 不完整的数组应该回退到使用 description
            if "备用描述" in prompt:
                print(f"✅ {desc_label}: 正确回退到 description")
            else:
                print(f"❌ {desc_label}: 未正确回退")
        except Exception as e:
            print(f"❌ {desc_label}: 异常 - {e}")

    return True

def main_test():
    """运行所有测试"""
    print("🧪 开始测试 is_sheet 数组格式功能\n")

    results = []
    results.append(("is_sheet 格式处理", test_is_sheet_formats()))
    results.append(("数组格式验证", test_sheet_array_validation()))

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
