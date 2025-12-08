"""
游戏素材图像生成工具
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv
import requests
import time
import numpy as np
from PIL import Image as PILImage

load_dotenv()  # 从 .env 加载到环境变量


# 初始化 OpenAI 客户端
client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=os.environ.get("ARK_API_KEY"),
)


# ==================== 配置区域 ====================

# 美术风格选择
ART_STYLE = "cartoon"  # pixel / cartoon / realistic

# 是否自动移除绿幕背景
AUTO_REMOVE_GREEN_SCREEN = True  # True=自动移除 / False=保持原样

# 绿幕移除选项
GREEN_SCREEN_CONFIG = {
    "skip_backgrounds": True,  # 是否跳过背景/插画类素材（background, illustration）
    "overwrite": True,  # 是否覆盖原文件（False则创建 _nobg 副本）
    "tolerance": 40,  # 绿色容差（0-100，数值越大移除范围越广）
    "threshold": 100,  # 绿色阈值（0-255，用于判断是否为绿色）
}

# ==================== 系统提示词 ====================

# 系统提示词模板（从 game_asset_prompts.py 迁移）
SYSTEM_PROMPTS = {
    # 基础提示词
    "base": "游戏素材，高质量，清晰，专业制作，PNG格式",

    # 风格提示词
    "pixel": "像素风格，8bit/16bit复古游戏风格，清晰的像素边界，游戏素材",
    "cartoon": "漫画风格，卡通渲染，cel-shading，明快色彩，游戏素材",
    "realistic": "写实风格，3D渲染，高细节，真实质感，游戏素材",

    # 分类提示词（不含绿幕，绿幕会根据need_green_screen动态添加）
    "char_portrait": "角色立绘，清晰轮廓，立绘设计，适合对话界面使用",
    "char_sprite": "角色小人，游戏精灵，清晰轮廓，适合游戏场景使用",
    "ui_asset": "UI组件，界面元素，清晰可辨识，扁平化设计",
    "sheet_effect": "序列帧特效，动态效果，连续帧设计，发光效果",
    "illustration": "插画设计，CG场景，完整构图，丰富细节",
    "logo": "标志设计，标题文字，清晰可辨识，品牌感",
    "prop": "道具物品，物品设计，清晰轮廓，适合游戏使用",
    "background": "背景设计，场景底图，层次分明",

    # 绿幕背景提示词（会根据need_green_screen动态添加）
    "green_screen": "纯绿色背景，绿幕背景，chroma key green background",
}


def build_prompt(description, category=None, style=None, need_green_screen=True):
    """
    构建完整提示词

    Args:
        description: 具体描述（必填）
        category: 分类 (character/ui/scene/effect)，可选
        style: 风格 (pixel/cartoon/realistic)，可选，默认使用 ART_STYLE
        need_green_screen: 是否需要绿幕背景，默认True

    Returns:
        str: 完整的提示词
    """
    parts = [description]

    # 添加分类系统提示词
    if category and category in SYSTEM_PROMPTS:
        parts.append(SYSTEM_PROMPTS[category])
    elif category == "none":
        # 如果明确指定 "none"，则不添加分类提示词
        pass

    # 强制添加绿幕背景（除非明确指定不需要）
    if need_green_screen:
        parts.append(SYSTEM_PROMPTS["green_screen"])

    # 添加风格提示词
    if style is None:
        style = ART_STYLE
    if style in SYSTEM_PROMPTS:
        parts.append(SYSTEM_PROMPTS[style])

    # 添加基础提示词
    parts.append(SYSTEM_PROMPTS["base"])

    # 用逗号连接所有部分
    return "，".join(parts)

# ==================== 加载任务配置 ====================

def load_tasks(config_file="tasks.json"):
    """
    从配置文件加载任务列表

    Args:
        config_file: 配置文件路径，默认为 tasks.json

    Returns:
        list: 任务列表
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        tasks = config.get('tasks', [])

        if not tasks:
            print(f"⚠️  警告: {config_file} 中的 tasks 数组为空")
            print(f"请在配置文件中添加要生成的图像任务")
            return []

        print(f"✅ 从 {config_file} 加载了 {len(tasks)} 个任务")
        return tasks

    except FileNotFoundError:
        print(f"❌ 错误: 找不到配置文件 {config_file}")
        print(f"请确保 {config_file} 文件存在于当前目录")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ 错误: {config_file} 格式错误")
        print(f"   {e}")
        return []
    except Exception as e:
        print(f"❌ 错误: 无法读取配置文件")
        print(f"   {e}")
        return []


# ==================== 智能尺寸计算函数 ====================

def calculate_api_size(target_size):
    """
    根据目标尺寸计算最佳的 API 调用尺寸

    规则：
    - 如果目标尺寸在 512x512 - 2048x2048 范围内，直接使用
    - 如果小于 512x512，放大到范围内（倍乘）
    - 如果大于 2048x2048，缩小到范围内（倍除）

    Args:
        target_size: 目标尺寸字符串，格式 "宽x高" (例如: "256x256")

    Returns:
        tuple: (api_size字符串, scale_factor浮点数, need_resize布尔值)
        - api_size: 用于 API 调用的尺寸字符串
        - scale_factor: 缩放因子（API尺寸/目标尺寸）
        - need_resize: 是否需要生成后缩放
    """
    try:
        # 解析目标尺寸
        if 'x' not in target_size.lower():
            return "1024x1024", 1.0, False

        width, height = map(int, target_size.lower().split('x'))

        # API 支持的尺寸范围
        MIN_SIZE = 512
        MAX_SIZE = 2048

        # 判断是否在支持范围内
        if MIN_SIZE <= width <= MAX_SIZE and MIN_SIZE <= height <= MAX_SIZE:
            # 在范围内，直接使用
            return target_size, 1.0, False

        # 计算缩放因子
        # 如果任一维度小于最小值，需要放大
        if width < MIN_SIZE or height < MIN_SIZE:
            # 计算需要放大的倍数（向上取整到 2 的幂次）
            scale_w = MIN_SIZE / width if width < MIN_SIZE else 1
            scale_h = MIN_SIZE / height if height < MIN_SIZE else 1
            scale_factor = max(scale_w, scale_h)

            # 向上取整到最接近的 2 的幂次（2, 4, 8...）
            import math
            scale_factor = 2 ** math.ceil(math.log2(scale_factor))

        # 如果任一维度大于最大值，需要缩小
        elif width > MAX_SIZE or height > MAX_SIZE:
            # 计算需要缩小的倍数（向上取整到 2 的幂次）
            scale_w = width / MAX_SIZE if width > MAX_SIZE else 1
            scale_h = height / MAX_SIZE if height > MAX_SIZE else 1
            scale_factor = max(scale_w, scale_h)

            # 向上取整到最接近的 2 的幂次
            import math
            scale_factor = 2 ** math.ceil(math.log2(scale_factor))

            # 缩小时 scale_factor 应该是 < 1 的（例如 0.5, 0.25）
            scale_factor = 1.0 / scale_factor
        else:
            scale_factor = 1.0

        # 计算 API 尺寸
        api_width = int(width * scale_factor)
        api_height = int(height * scale_factor)

        # 确保 API 尺寸在范围内
        api_width = max(MIN_SIZE, min(MAX_SIZE, api_width))
        api_height = max(MIN_SIZE, min(MAX_SIZE, api_height))

        api_size = f"{api_width}x{api_height}"
        need_resize = (api_width != width or api_height != height)

        return api_size, scale_factor, need_resize

    except Exception as e:
        print(f"⚠️ 尺寸计算失败: {e}")
        return "1024x1024", 1.0, False


# ==================== 图像缩放函数 ====================

def resize_image(filepath, target_size, name):
    """
    缩放图像到目标尺寸

    使用高质量的 LANCZOS 重采样算法，支持放大和缩小

    Args:
        filepath: 图像文件路径
        target_size: 目标尺寸，格式为 "宽x高" (例如: "2048x2048")
        name: 素材名称

    Returns:
        tuple: (是否成功, 原始尺寸, 目标尺寸)
    """
    try:
        # 解析目标尺寸
        if 'x' not in target_size.lower():
            return False, None, None

        width, height = map(int, target_size.lower().split('x'))

        # 打开图像
        img = PILImage.open(filepath)
        original_size = img.size

        # 如果尺寸已经匹配，跳过缩放
        if img.size == (width, height):
            return True, original_size, (width, height)

        # 使用高质量的重采样算法
        # LANCZOS 适合缩小，对放大也有不错的效果
        resized_img = img.resize((width, height), PILImage.Resampling.LANCZOS)

        # 保存缩放后的图像
        resized_img.save(filepath, 'PNG')

        return True, original_size, (width, height)

    except Exception as e:
        print(f"         ⚠️  图像缩放失败: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None


# ==================== 背景移除函数 ====================

def remove_green_screen(filepath, name, skip_backgrounds=True, overwrite=True, tolerance=40, threshold=100, category=None):
    """
    移除绿幕背景（Chroma Key）

    使用 HSV 色彩空间检测绿色并将其设为透明

    Args:
        filepath: 图像文件路径
        name: 素材名称
        skip_backgrounds: 是否跳过背景/插画素材
        overwrite: 是否覆盖原文件
        tolerance: 绿色容差（0-100，数值越大移除范围越广）
        threshold: 绿色阈值（0-255，用于判断G通道强度）
        category: 素材分类（用于判断是否为 background 或 illustration）

    Returns:
        tuple: (是否成功, 处理的像素数)
    """
    # 检查是否为背景素材（只有 background 和 illustration 不需要抠图）
    no_green_screen_categories = ["background", "illustration"]
    is_background = category in no_green_screen_categories

    if skip_backgrounds and is_background:
        return False, 0  # 跳过背景/插画素材

    try:
        # 打开图像
        img = PILImage.open(filepath)

        # 转换为RGBA模式
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # 转换为numpy数组
        img_array = np.array(img, dtype=np.float32)
        h, w = img_array.shape[:2]

        # 提取RGB通道
        r = img_array[:, :, 0]
        g = img_array[:, :, 1]
        b = img_array[:, :, 2]

        # 绿幕检测逻辑：
        # 1. G通道值要高（绿色强）
        # 2. G通道明显高于R和B通道（绿色主导）
        # 3. 整体亮度不能太低（避免黑色）

        # 条件1: 绿色通道足够强
        green_strong = g > threshold

        # 条件2: 绿色明显高于红色和蓝色
        green_dominant = (g > r + tolerance) & (g > b + tolerance)

        # 条件3: 避免太暗的像素（黑色）
        brightness = (r + g + b) / 3
        not_too_dark = brightness > 30

        # 组合所有条件
        is_green = green_strong & green_dominant & not_too_dark

        # 将检测到的绿色像素设为透明
        img_array[is_green, 3] = 0

        # 转换回uint8
        img_array = np.clip(img_array, 0, 255).astype(np.uint8)

        # 转换回PIL图像
        result_img = PILImage.fromarray(img_array, 'RGBA')

        # 保存结果
        if overwrite:
            result_img.save(filepath, 'PNG')
        else:
            # 创建 _nobg 副本
            from pathlib import Path
            path_obj = Path(filepath)
            nobg_path = path_obj.parent / f"{path_obj.stem}_nobg{path_obj.suffix}"
            result_img.save(str(nobg_path), 'PNG')

        pixels_removed = int(np.sum(is_green))
        return True, pixels_removed

    except Exception as e:
        print(f"         ⚠️  绿幕移除失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


# ==================== 主生成函数 ====================

def generate_images(tasks, output_dir="./generated-images"):
    """
    批量生成图像

    Args:
        tasks: 生成任务列表，每个任务包含 name 和 prompt
        output_dir: 输出目录
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    full_output_dir = output_dir

    print(f"开始生成 {len(tasks)} 张图像...")
    print(f"默认美术风格: {ART_STYLE}（可由任务参数覆盖）")
    print(f"自动移除绿幕: {'✅ 开启' if AUTO_REMOVE_GREEN_SCREEN else '❌ 关闭'}")
    print(f"输出目录: {full_output_dir}")
    print("="*80)

    success_count = 0
    fail_count = 0
    errors = []  # 记录错误信息
    images_info = []  # 记录生成的图像信息（仅用于返回值，不保存到文件）

    for idx, task in enumerate(tasks, 1):
        name = task["name"]

        # 支持两种方式：
        # 1. 直接提供 prompt
        # 2. 使用 description + category 自动构建
        if "prompt" in task:
            prompt = task["prompt"]
            actual_style = task.get("style", ART_STYLE)  # 记录实际风格
        elif "description" in task:
            actual_style = task.get("style", ART_STYLE)  # 记录实际风格
            prompt = build_prompt(
                description=task["description"],
                category=task.get("category"),
                style=actual_style,
                need_green_screen=task.get("need_green_screen", True)
            )
        else:
            error_msg = f"缺少 prompt 或 description"
            print(f"[{idx}/{len(tasks)}] ❌ 跳过 {name} - {error_msg}")
            errors.append({"name": name, "error": error_msg})
            fail_count += 1
            continue

        if not prompt:
            error_msg = f"无效的提示词"
            print(f"[{idx}/{len(tasks)}] ❌ 跳过 {name} - {error_msg}")
            errors.append({"name": name, "error": error_msg})
            fail_count += 1
            continue

        # 获取目标图像尺寸
        target_size = task.get("size", "1024x1024")

        # 计算最佳 API 尺寸
        api_size, scale_factor, need_resize = calculate_api_size(target_size)

        print(f"\n[{idx}/{len(tasks)}] 正在生成: {name}")
        print(f"使用风格: {actual_style}")
        print(f"目标尺寸: {target_size}")
        print(f"API 生成尺寸: {api_size}")
        if need_resize:
            print(f"缩放策略: {api_size} → {target_size} (缩放因子: {scale_factor:.2f}x)")
        else:
            print(f"缩放策略: 直接使用目标尺寸，无需后处理")
        print(f"提示词: {prompt[:100]}..." if len(prompt) > 100 else f"提示词: {prompt}")

        try:
            # 调用豆包图像生成 API（使用智能计算的尺寸）
            imagesResponse = client.images.generate(
                # model="doubao-seedream-4-0-250828",
                model="doubao-seedream-3-0-t2i-250415",
                prompt=prompt,
                size=api_size,  # 使用智能计算的 API 尺寸
                response_format="url",
                extra_body={
                    "watermark": False,  # 设置为 False 移除水印
                },
            )

            img_url = imagesResponse.data[0].url

            # 下载图片
            response = requests.get(img_url, timeout=30)

            if response.status_code == 200:
                # 直接使用素材名称，不添加时间戳（目录名已包含时间戳）
                filename = f"{full_output_dir}/{name}.png"

                with open(filename, "wb") as f:
                    f.write(response.content)

                print(f"✅ 成功保存: {filename}")

                # 自动移除背景
                green_removed = False
                pixels_removed = 0
                if AUTO_REMOVE_GREEN_SCREEN:
                    print(f"🔄 移除绿幕中...")
                    green_removed, pixels_removed = remove_green_screen(
                        filename,
                        name,
                        GREEN_SCREEN_CONFIG["skip_backgrounds"],
                        GREEN_SCREEN_CONFIG["overwrite"],
                        GREEN_SCREEN_CONFIG["tolerance"],
                        GREEN_SCREEN_CONFIG["threshold"],
                        task.get("category")  # 传递 category 参数用于判断背景图
                    )
                    if green_removed and pixels_removed > 0:
                        print(f"✅ 绿幕已移除 (处理了 {pixels_removed:,} 个像素)")
                    elif green_removed and pixels_removed == 0:
                        print(f"ℹ️  未检测到绿幕")
                    else:
                        # green_removed == False 说明跳过了（background 或 illustration）
                        print(f"⏭️  跳过抠图（背景/插画类素材）")

                # 缩放图像到目标尺寸（如需要）
                resized = False
                original_size = None
                final_size = None
                if need_resize:
                    print(f"🔄 缩放图像: {api_size} → {target_size}...")
                    resized, original_size, final_size = resize_image(filename, target_size, name)
                    if resized:
                        print(f"✅ 图像已缩放: {original_size} → {final_size}")
                    else:
                        print(f"⚠️  图像缩放失败")
                else:
                    print(f"ℹ️  尺寸已匹配，跳过缩放")
                    resized = True
                    # 解析 API 尺寸作为原始尺寸
                    api_w, api_h = map(int, api_size.lower().split('x'))
                    original_size = (api_w, api_h)
                    final_size = (api_w, api_h)

                # 记录图像信息（仅用于返回值）
                images_info.append({
                    "filename": f"{name}.png",
                    "name": name,
                    "prompt": prompt,
                    "style": actual_style,
                    "target_size": target_size,
                    "api_size": api_size,
                    "scale_factor": scale_factor,
                    "green_screen_removed": green_removed,
                    "pixels_removed": pixels_removed,
                    "resized": need_resize,
                    "original_size": f"{original_size[0]}x{original_size[1]}" if original_size else None,
                    "final_size": f"{final_size[0]}x{final_size[1]}" if final_size else None
                })

                success_count += 1

            else:
                error_msg = f"图片下载失败，状态码: {response.status_code}"
                print(f"❌ {error_msg}")
                errors.append({"name": name, "error": error_msg})
                fail_count += 1

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"❌ 生成失败: {error_msg}")
            errors.append({"name": name, "error": error_msg})
            fail_count += 1

    # 输出统计信息
    print("\n" + "="*80)
    print(f"生成完成！")
    print(f"✅ 成功: {success_count} 个")
    print(f"❌ 失败: {fail_count} 个")
    print(f"📁 保存位置: {full_output_dir}/")

    # 返回生成结果（供MCP服务器使用）
    return {
        "success": success_count > 0,
        "success_count": success_count,
        "fail_count": fail_count,
        "output_dir": full_output_dir,
        "images": images_info,  # 图像信息（仅用于返回值，不保存到文件）
        "errors": errors,  # 错误信息列表
        "total": len(tasks)
    }


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    # 从配置文件加载任务
    tasks = load_tasks("tasks.json")

    if tasks:
        generate_images(tasks)
    else:
        print("错误: 没有可执行的任务！")
        print("请检查 tasks.json 文件并添加任务。")
