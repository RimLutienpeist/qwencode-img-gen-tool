"""
游戏素材图像生成工具
"""

import os
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv
import requests
import time
import numpy as np
from PIL import Image as PILImage
import cv2

# 配置日志
# logging.disable(logging.CRITICAL)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()  # 从 .env 加载到环境变量


# 初始化 OpenAI 客户端
client = OpenAI(
    base_url=os.environ.get("ARK_BASE_URL"),
    api_key=os.environ.get("ARK_API_KEY"),
)


# ==================== 配置区域 ====================


MODEL_NAME = os.environ.get("ARK_MODEL", "")

# 模型尺寸范围配置
MODEL_SIZE_RANGES = {
    "doubao-seedream-3-0-t2i-250415": {
        "min_width": 512,
        "min_height": 512,
        "max_width": 2048,
        "max_height": 2048
    },
    "doubao-seedream-4-0-250828": {
        "min_width": 1280,
        "min_height": 720,
        "max_width": 4096,
        "max_height": 4096
    },
    "doubao-seedream-4-5-251128": {
        "min_width": 2560,
        "min_height": 1440,
        "max_width": 4096,
        "max_height": 4096
    }
}

# 美术风格选择
ART_STYLE = "cartoon"  # pixel / cartoon / realistic

# 是否自动移除背景
AUTO_REMOVE_BACKGROUND = True  # True=自动移除 / False=保持原样

# 测试模式配置（仅用于 if __name__ == "__main__" 时）
TEST_MODE = {
    "enabled": True,  # True=测试模式 / False=正常模式
    "use_api": True,  # True=使用API生成图像 / False=处理本地图像
    "tasks_config": "../test/tasks.json",  # tasks.json 配置文件路径（use_api=True时使用）
    "input_directory": "../test/",  # 本地图像目录（use_api=False时使用）
    "output_directory": "../test_output/",  # 输出目录
    "target_size": None,  # 目标尺寸（None=保持原尺寸）
}

# 背景移除选项
BACKGROUND_REMOVAL_CONFIG = {
    "skip_backgrounds": True,  # 是否跳过背景/插画类素材（background, illustration）
    "overwrite": True,  # 是否覆盖原文件（False则创建 _nobg 副本）
    "tolerance": 5,  # 颜色容差（欧氏距离阈值，降低以保留前景白色）
    "threshold": 250,  # 白色阈值（0-255，提高以只移除非常纯的白色）
    "algorithm": "grabcut",  # 算法选择: "simple" 或 "grabcut"
    "grabcut_iterations": 5,  # GrabCut 迭代次数（1-10，数值越大效果越好但越慢）
    "edge_feather": 1,  # 边缘羽化半径（像素，0 表示不羽化）
    "remove_color_spill": True,  # 是否移除颜色溢出（边缘色彩校正）
    "auto_detect_background": True,  # 启用自动检测背景色（支持黑/白/蓝/灰等任意纯色背景）
    "use_edge_detection": True,  # 启用边缘检测辅助（保护前景中的背景色）
}

# ==================== 系统提示词 ====================

# 系统提示词模板
SYSTEM_PROMPTS = {
    # 基础提示词
    "base": "游戏素材，高质量，清晰，专业制作，PNG格式，避免在图像内部使用纯白色",

    # 风格提示词
    "pixel": "像素风格，8bit/16bit复古游戏风格，清晰的像素边界，游戏素材",
    "cartoon": "漫画风格，卡通渲染，cel-shading，明快色彩，游戏素材",
    "realistic": "写实风格，3D渲染，高细节，真实质感，游戏素材",

    # 分类提示词（不含白色背景，白色背景会根据need_white_background动态添加）
    "char_portrait": "角色立绘，清晰轮廓，立绘设计，适合对话界面使用",
    "char_sprite": "角色小人，游戏精灵，清晰轮廓，适合游戏场景使用",
    "ui_asset": "UI组件，界面元素，清晰可辨识，扁平化设计",
    "effect": "特效元素，视觉效果",
    "illustration": "插画设计，CG场景，完整构图，丰富细节",
    "logo": "标志设计，标题文字，清晰可辨识，品牌感，必须使用纯白色背景",
    "prop": "道具物品，物品设计，清晰轮廓，适合游戏使用",
    "background": "背景设计，场景底图，层次分明",

    # 纯白背景提示词（会根据need_white_background动态添加）
    "white_background": "纯白色背景，纯白底色，plain white background，solid white backdrop",
}


def build_prompt(description, category=None, style=None, need_white_background=True):
    """
    构建完整提示词

    Args:
        description: 具体描述（必填）
        category: 分类 (character/ui/scene/effect)，可选
        style: 风格 (pixel/cartoon/realistic)，可选，默认使用 ART_STYLE
        need_white_background: 是否需要纯白背景，默认True

    Returns:
        str: 完整的提示词
    """
    parts = []

    # 优先添加白色背景要求（放在最前面，提高优先级）
    if need_white_background:
        parts.append(SYSTEM_PROMPTS["white_background"])

    # 添加用户描述
    parts.append(description)

    # 添加分类系统提示词
    if category and category in SYSTEM_PROMPTS:
        parts.append(SYSTEM_PROMPTS[category])
    elif category == "none":
        # 如果明确指定 "none"，则不添加分类提示词
        pass

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
            logger.warning(f"{config_file} 中的 tasks 数组为空")
            logger.info(f"请在配置文件中添加要生成的图像任务")
            return []

        logger.info(f"从 {config_file} 加载了 {len(tasks)} 个任务")
        return tasks

    except FileNotFoundError:
        logger.error(f"找不到配置文件 {config_file}")
        logger.info(f"请确保 {config_file} 文件存在于当前目录")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"{config_file} 格式错误")
        logger.info(f"   {e}")
        return []
    except Exception as e:
        logger.error(f"无法读取配置文件")
        logger.info(f"   {e}")
        return []


# ==================== 智能尺寸计算函数 ====================

def calculate_api_size(target_size, model_name=None):
    """
    根据目标尺寸和模型配置计算最佳的 API 调用尺寸

    规则：
    - 如果目标尺寸在模型支持的范围内，直接使用
    - 如果小于最小尺寸，放大到范围内（倍乘）
    - 如果大于最大尺寸，缩小到范围内（倍除）

    Args:
        target_size: 目标尺寸字符串，格式 "宽x高" (例如: "256x256")
        model_name: 模型名称，默认使用 MODEL_NAME

    Returns:
        tuple: (api_size字符串, scale_factor浮点数, need_resize布尔值)
        - api_size: 用于 API 调用的尺寸字符串
        - scale_factor: 缩放因子（API尺寸/目标尺寸）
        - need_resize: 是否需要生成后缩放
    """
    try:
        # 使用默认模型或指定模型
        if model_name is None:
            model_name = MODEL_NAME

        # 获取模型配置
        if model_name not in MODEL_SIZE_RANGES:
            logger.warning(f"⚠️  模型 {model_name} 未配置，使用默认范围")
            model_config = MODEL_SIZE_RANGES["doubao-seedream-3-0-t2i-250415"]
        else:
            model_config = MODEL_SIZE_RANGES[model_name]

        MIN_WIDTH = model_config["min_width"]
        MIN_HEIGHT = model_config["min_height"]
        MAX_WIDTH = model_config["max_width"]
        MAX_HEIGHT = model_config["max_height"]

        # 解析目标尺寸
        if 'x' not in target_size.lower():
            return f"{MIN_WIDTH}x{MIN_HEIGHT}", 1.0, False

        width, height = map(int, target_size.lower().split('x'))

        # 判断是否在支持范围内
        if MIN_WIDTH <= width <= MAX_WIDTH and MIN_HEIGHT <= height <= MAX_HEIGHT:
            # 在范围内，直接使用
            return target_size, 1.0, False

        # 计算缩放因子
        # 如果任一维度小于最小值，需要放大
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            # 计算需要放大的倍数（向上取整到 2 的幂次）
            scale_w = MIN_WIDTH / width if width < MIN_WIDTH else 1
            scale_h = MIN_HEIGHT / height if height < MIN_HEIGHT else 1
            scale_factor = max(scale_w, scale_h)

            # 向上取整到最接近的 2 的幂次（2, 4, 8...）
            import math
            scale_factor = 2 ** math.ceil(math.log2(scale_factor))

        # 如果任一维度大于最大值，需要缩小
        elif width > MAX_WIDTH or height > MAX_HEIGHT:
            # 计算需要缩小的倍数（向上取整到 2 的幂次）
            scale_w = width / MAX_WIDTH if width > MAX_WIDTH else 1
            scale_h = height / MAX_HEIGHT if height > MAX_HEIGHT else 1
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
        api_width = max(MIN_WIDTH, min(MAX_WIDTH, api_width))
        api_height = max(MIN_HEIGHT, min(MAX_HEIGHT, api_height))

        api_size = f"{api_width}x{api_height}"
        need_resize = (api_width != width or api_height != height)

        return api_size, scale_factor, need_resize

    except Exception as e:
        logger.error(f"尺寸计算失败: {e}")
        return "1024x1024", 1.0, False


# ==================== 图像缩放函数 ====================

def resize_image(filepath, target_size, name, keep_aspect_ratio=True):
    """
    缩放图像到目标尺寸

    使用高质量的 LANCZOS 重采样算法，支持放大和缩小
    支持保持比例缩放：最短边对齐目标最短边，长边按比例缩放

    Args:
        filepath: 图像文件路径
        target_size: 目标尺寸，格式为 "宽x高" (例如: "2048x2048")
        name: 素材名称
        keep_aspect_ratio: 是否保持比例缩放（True=最短边对齐，False=强制拉伸）

    Returns:
        tuple: (是否成功, 原始尺寸, 最终尺寸)
    """
    try:
        # 解析目标尺寸
        if 'x' not in target_size.lower():
            return False, None, None

        target_width, target_height = map(int, target_size.lower().split('x'))

        # 打开图像
        img = PILImage.open(filepath)
        original_size = img.size
        orig_width, orig_height = original_size

        # 如果尺寸已经匹配，跳过缩放
        if img.size == (target_width, target_height):
            return True, original_size, (target_width, target_height)

        if keep_aspect_ratio:
            # 按比例缩放：最短边对齐目标尺寸的最短边，长边按比例缩放

            # 计算目标的最短边和最长边
            target_min = min(target_width, target_height)
            target_max = max(target_width, target_height)

            # 计算原始图像的最短边和最长边
            orig_min = min(orig_width, orig_height)
            orig_max = max(orig_width, orig_height)

            # 计算缩放比例：原始最短边 → 目标最短边
            scale_ratio = target_min / orig_min

            # 计算新的尺寸（保持原始比例）
            new_width = int(orig_width * scale_ratio)
            new_height = int(orig_height * scale_ratio)

            # 确定目标尺寸是横向还是纵向
            target_is_landscape = target_width >= target_height
            orig_is_landscape = orig_width >= orig_height

            # 如果原图和目标的方向不同，可能需要调整
            # 但我们保持原图比例，所以直接使用计算出的尺寸
            final_width = new_width
            final_height = new_height

            logger.info(f"         按比例缩放: {orig_width}x{orig_height} → {final_width}x{final_height} (比例 {scale_ratio:.3f}x)")

        else:
            # 强制拉伸到目标尺寸（不保持比例）
            final_width = target_width
            final_height = target_height
            logger.info(f"         强制缩放: {orig_width}x{orig_height} → {final_width}x{final_height}")

        # 使用高质量的重采样算法
        # LANCZOS 适合缩小，对放大也有不错的效果
        resized_img = img.resize((final_width, final_height), PILImage.Resampling.LANCZOS)

        # 保存缩放后的图像
        resized_img.save(filepath, 'PNG')

        return True, original_size, (final_width, final_height)

    except Exception as e:
        logger.error(f"         图像缩放失败: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None


# ==================== 背景移除函数 ====================

def detect_background_color(img, debug=False):
    """
    通过采样图像边缘和角落区域自动检测背景色

    Args:
        img: OpenCV 图像 (BGR 格式)
        debug: 是否输出调试信息

    Returns:
        tuple: (bg_color, bg_std, is_pure)
            - bg_color: 背景颜色 (B, G, R) numpy array
            - bg_std: 标准差（判断背景纯度）
            - is_pure: 背景是否纯净（True/False）
    """
    h, w = img.shape[:2]

    # 1. 计算边缘采样宽度（至少 10 像素，最多图像宽高的 10%）
    border_width = max(10, min(w, h) // 10)

    # 2. 采样边缘区域
    edge_samples = []
    edge_samples.append(img[0:border_width, :])           # 上边缘
    edge_samples.append(img[-border_width:, :])           # 下边缘
    edge_samples.append(img[:, 0:border_width])           # 左边缘
    edge_samples.append(img[:, -border_width:])           # 右边缘

    # 3. 采样四个角落（20x20 区域）
    corner_size = min(20, min(w, h) // 10)
    corners = [
        img[0:corner_size, 0:corner_size],                # 左上
        img[0:corner_size, -corner_size:],                # 右上
        img[-corner_size:, 0:corner_size],                # 左下
        img[-corner_size:, -corner_size:]                 # 右下
    ]

    # 4. 合并所有采样（reshape 为 (N, 3)）
    all_samples = []
    for sample in edge_samples + corners:
        all_samples.append(sample.reshape(-1, 3))
    all_samples = np.vstack(all_samples)

    # 5. 计算中位数作为背景色（比均值更鲁棒，抗干扰）
    bg_color = np.median(all_samples, axis=0).astype(np.uint8)

    # 6. 计算标准差（判断背景纯度）
    bg_std = np.std(all_samples.astype(np.float32), axis=0).mean()

    # 7. 判断背景是否纯净（标准差 < 30 为纯净）
    is_pure = bg_std < 30

    if debug:
        logger.debug(f"         背景检测: BGR={bg_color}, 标准差={bg_std:.1f}, 纯净度={'✓' if is_pure else '✗'}")

    return bg_color, bg_std, is_pure


def is_background_color(img, bg_color, tolerance=40):
    """
    检测像素是否为背景色（基于欧氏距离）

    Args:
        img: 图像 (H, W, 3)
        bg_color: 背景颜色 (B, G, R)
        tolerance: 容差（欧氏距离阈值）

    Returns:
        mask: 布尔数组 (H, W)，True 表示背景像素
    """
    # 计算每个像素与背景色的欧氏距离
    diff = img.astype(np.float32) - bg_color.astype(np.float32)
    distance = np.sqrt(np.sum(diff ** 2, axis=2))

    # 距离小于容差 = 背景
    return distance < tolerance


def remove_white_background_simple(filepath, name, skip_backgrounds=True, overwrite=True, tolerance=40, threshold=200, category=None):
    """
    移除白色背景（简单算法）

    使用简单的颜色阈值检测白色并将其设为透明（硬边缘）

    Args:
        filepath: 图像文件路径
        name: 素材名称
        skip_backgrounds: 是否跳过背景/插画素材
        overwrite: 是否覆盖原文件
        tolerance: 颜色容差（0-100，数值越大移除范围越广）
        threshold: 白色阈值（0-255，用于判断亮度，建议 200-240）
        category: 素材分类（用于判断是否为 background 或 illustration）

    Returns:
        tuple: (是否成功, 处理的像素数)
    """
    # 检查是否为背景素材（只有 background 和 illustration 不需要抠图）
    # no_background_removal_categories = ["background", "illustration"]
    no_background_removal_categories = ["background"]
    is_background = category in no_background_removal_categories

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

        # 白色背景检测逻辑：
        # 1. 所有通道值都要高（RGB 都接近 255）
        # 2. RGB 三个通道的值相近（颜色接近灰度）
        # 3. 整体亮度足够高

        # 计算整体亮度
        brightness = (r + g + b) / 3

        # 条件1: 亮度足够高（接近白色）
        is_bright = brightness > threshold

        # 条件2: RGB 通道值相近（接近灰度，避免彩色）
        # 计算最大和最小通道的差异
        max_channel = np.maximum(np.maximum(r, g), b)
        min_channel = np.minimum(np.minimum(r, g), b)
        color_diff = max_channel - min_channel

        # 颜色差异要小（表示接近灰度/白色）
        is_neutral = color_diff < tolerance

        # 组合所有条件
        is_white = is_bright & is_neutral

        # 将检测到的白色像素设为透明
        img_array[is_white, 3] = 0

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

        pixels_removed = int(np.sum(is_white))
        return True, pixels_removed

    except Exception as e:
        logger.error(f"         背景移除失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def remove_white_background_grabcut(filepath, name, skip_backgrounds=True, overwrite=True,
                                    tolerance=40, threshold=200, category=None,
                                    iterations=5, edge_feather=3, remove_spill=True,
                                    auto_detect=True, use_edge_detection=False):
    """
    移除背景（GrabCut 算法 - 支持自适应背景色检测）

    使用 OpenCV 的 GrabCut 图割算法进行智能抠图，支持边缘羽化和颜色溢出去除

    Args:
        filepath: 图像文件路径
        name: 素材名称
        skip_backgrounds: 是否跳过背景/插画素材
        overwrite: 是否覆盖原文件
        tolerance: 颜色容差（欧氏距离阈值，建议 30-60）
        threshold: 白色阈值（0-255，仅在 auto_detect=False 时使用）
        category: 素材分类（用于判断是否为 background 或 illustration）
        iterations: GrabCut 迭代次数（1-10，数值越大效果越好但越慢）
        edge_feather: 边缘羽化半径（像素，0 表示不羽化）
        remove_spill: 是否移除颜色溢出
        auto_detect: 是否自动检测背景色（True=自适应，False=固定白色）

    Returns:
        tuple: (是否成功, 处理的像素数)
    """
    # 检查是否为背景素材
    # no_background_removal_categories = ["background", "illustration"]
    no_background_removal_categories = ["background"]
    is_background = category in no_background_removal_categories

    if skip_backgrounds and is_background:
        return False, 0

    try:
        # 读取图像
        img = cv2.imread(filepath)
        if img is None:
            raise ValueError(f"无法读取图像: {filepath}")

        # 获取图像尺寸
        height, width = img.shape[:2]

        # ==================== 步骤 0: 边缘检测辅助（可选）====================

        # 使用边缘检测来辅助识别主体物体（从配置读取）
        subject_mask = None  # 主体掩码：完全确定的前景区域

        if use_edge_detection:
            logger.info(f"         使用边缘检测识别图像主体...")

            # 转换为灰度图
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 方法1: Canny 边缘检测
            edges = cv2.Canny(gray, 30, 100)  # 降低阈值，更敏感

            # 形态学闭运算（连接断裂的边缘）
            kernel_close = np.ones((5, 5), np.uint8)
            edges_closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_close, iterations=3)

            # 方法2: 自适应阈值（辅助检测）
            adaptive_thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
            )

            # 方法3: Otsu阈值
            _, otsu_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # 融合三种方法的结果
            combined_edges = cv2.bitwise_or(edges_closed, adaptive_thresh)
            combined_edges = cv2.bitwise_or(combined_edges, otsu_thresh)

            # 形态学操作：填充小孔洞
            kernel_fill = np.ones((7, 7), np.uint8)
            combined_edges = cv2.morphologyEx(combined_edges, cv2.MORPH_CLOSE, kernel_fill, iterations=2)

            # 查找轮廓
            contours, _ = cv2.findContours(combined_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                # 计算每个轮廓的特征
                valid_contours = []
                margin = 10  # 边距阈值（像素）
                min_area = (width * height) * 0.01  # 最小面积：图像的1%

                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area < min_area:
                        continue  # 太小的轮廓忽略

                    x, y, w, h = cv2.boundingRect(contour)

                    # 检查是否接近图像边界
                    is_edge_contour = (
                        x < margin or
                        y < margin or
                        x + w > width - margin or
                        y + h > height - margin
                    )

                    # 计算轮廓的紧密度（周长^2 / 面积，圆形约为12.57）
                    perimeter = cv2.arcLength(contour, True)
                    compactness = (perimeter ** 2) / area if area > 0 else float('inf')

                    # 只保留不在边缘的轮廓，且紧密度合理
                    if not is_edge_contour and compactness < 100:
                        valid_contours.append((contour, area))

                if valid_contours:
                    # 找到面积最大的有效轮廓（假设是主体物体）
                    largest_contour, largest_area = max(valid_contours, key=lambda x: x[1])

                    # 创建主体掩码（轮廓内部=1，外部=0）
                    subject_mask = np.zeros((height, width), dtype=np.uint8)
                    cv2.drawContours(subject_mask, [largest_contour], -1, 1, thickness=cv2.FILLED)

                    # 改进：使用更温和的腐蚀（只腐蚀2-5像素）
                    # 根据图像大小动态调整腐蚀核大小
                    erode_size = max(2, min(5, int(min(width, height) * 0.01)))
                    kernel_erode = np.ones((erode_size, erode_size), np.uint8)
                    subject_core = cv2.erode(subject_mask, kernel_erode, iterations=1)

                    contour_area = largest_area
                    core_area = np.sum(subject_core)
                    image_area = height * width
                    area_ratio = contour_area / image_area

                    logger.info(f"         边缘检测: 找到主体轮廓，面积={contour_area:.0f}px² ({area_ratio*100:.1f}%)")
                    logger.info(f"         边缘检测: 腐蚀核大小={erode_size}x{erode_size}，核心区域={core_area:.0f}px² ({core_area/image_area*100:.1f}%)")

                    # 将整个主体轮廓作为掩码（不只是核心区域）
                    subject_mask = subject_mask.astype(bool)
                else:
                    logger.info(f"         边缘检测: 未找到有效轮廓")
            else:
                logger.info(f"         边缘检测: 未检测到任何轮廓")

        # ==================== 步骤 1: 颜色检测生成初步掩码 ====================

        # 提取 RGB 通道（OpenCV 使用 BGR 格式）
        b, g, r = cv2.split(img)

        if auto_detect:
            # 模式 A: 自适应背景色检测
            logger.info(f"         使用自适应背景检测...")
            bg_color, bg_std, is_pure = detect_background_color(img, debug=True)

            # 如果背景不纯净，提示警告但继续处理
            if not is_pure:
                logger.warning(f"         背景不够纯净（标准差={bg_std:.1f}），可能影响抠图效果")

            # 基于检测到的背景色生成掩码
            is_bg = is_background_color(img, bg_color, tolerance=tolerance)

            # 计算距离用于判断明确前景
            diff = img.astype(np.float32) - bg_color.astype(np.float32)
            distance = np.sqrt(np.sum(diff ** 2, axis=2))

            # 明确前景：距离背景色较远的区域
            # 使用动态阈值：tolerance * 2 作为前景判断阈值
            is_definite_fg = distance > (tolerance * 2)

        else:
            # 模式 B: 固定白色检测（原有逻辑）
            brightness = (r.astype(np.float32) + g.astype(np.float32) + b.astype(np.float32)) / 3
            is_bright = brightness > threshold

            # RGB 通道值相近（接近灰度/白色）
            max_channel = np.maximum(np.maximum(r, g), b)
            min_channel = np.minimum(np.minimum(r, g), b)
            color_diff = max_channel - min_channel
            is_neutral = color_diff < tolerance

            is_bg = is_bright & is_neutral

            # 明确的前景（非白色且亮度较低的区域）
            is_definite_fg = ~is_bg & (brightness < threshold - 50)

        # 创建 GrabCut 掩码
        # GrabCut 使用 4 个值：
        # 0 = GC_BGD (明确背景)
        # 1 = GC_FGD (明确前景)
        # 2 = GC_PR_BGD (可能背景)
        # 3 = GC_PR_FGD (可能前景)
        mask = np.full((height, width), cv2.GC_PR_FGD, dtype=np.uint8)  # 默认为可能前景

        # 明确的背景（颜色检测）
        mask[is_bg] = cv2.GC_BGD

        # ==================== 关键改进：主体区域强制前景 ====================
        # 如果有主体检测结果，将主体内部的所有像素强制标记为前景
        if subject_mask is not None:
            # 主体轮廓内的所有像素（包括白色）都标记为确定前景
            mask[subject_mask] = cv2.GC_FGD

            # 主体外部的背景色区域标记为确定背景
            mask[~subject_mask & is_bg] = cv2.GC_BGD

            protected_pixels = np.sum(subject_mask)
            white_in_subject = np.sum(subject_mask & is_bg)
            logger.info(f"         主体保护: 主体内部{protected_pixels:,}个像素标记为前景")
            logger.info(f"         主体保护: 其中{white_in_subject:,}个白色像素被保护（不会被移除）")

        # 腐蚀操作找出核心前景区域（避免边缘误判）
        # 注意：只对非主体区域应用腐蚀，主体区域已经被保护
        if subject_mask is None:
            kernel = np.ones((5, 5), np.uint8)
            is_definite_fg = cv2.erode(is_definite_fg.astype(np.uint8), kernel, iterations=1).astype(bool)
            mask[is_definite_fg] = cv2.GC_FGD

        # ==================== 步骤 2: GrabCut 迭代优化 ====================

        # 初始化 GrabCut 模型
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)

        # 运行 GrabCut 算法
        try:
            cv2.grabCut(img, mask, None, bgd_model, fgd_model, iterations, cv2.GC_INIT_WITH_MASK)
        except cv2.error as e:
            logger.warning(f"         GrabCut 算法失败，回退到简单算法: {e}")
            # 如果 GrabCut 失败，使用简单的颜色检测
            pass

        # 生成二值掩码（前景 = 1，背景 = 0）
        # mask 的值：0,2 表示背景，1,3 表示前景
        binary_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)

        # 检查主体区域是否被保留
        if subject_mask is not None:
            subject_preserved = np.sum(binary_mask[subject_mask]) / np.sum(subject_mask)
            logger.info(f"         GrabCut完成: 主体区域保留率={subject_preserved*100:.1f}%")

        # ==================== 步骤 3: 边缘羽化 ====================

        alpha_mask = binary_mask.copy().astype(np.float32) * 255

        if edge_feather > 0:
            # 找出边缘区域
            kernel = np.ones((3, 3), np.uint8)
            dilated = cv2.dilate(binary_mask, kernel, iterations=edge_feather)
            eroded = cv2.erode(binary_mask, kernel, iterations=edge_feather)
            edge_region = dilated - eroded

            # 计算距离变换（从边缘的距离）
            dist_transform = cv2.distanceTransform(binary_mask, cv2.DIST_L2, 5)

            # 在边缘区域应用距离变换生成渐变
            # 归一化距离变换到 0-1 范围
            if dist_transform.max() > 0:
                dist_normalized = dist_transform / (edge_feather + 1)
                dist_normalized = np.clip(dist_normalized, 0, 1)

                # 在边缘区域应用渐变
                alpha_mask = np.where(edge_region > 0,
                                     dist_normalized * 255,
                                     alpha_mask)

            # 应用高斯模糊柔化边缘
            alpha_mask = cv2.GaussianBlur(alpha_mask, (0, 0), sigmaX=edge_feather/2)

        # 确保 alpha 值在 0-255 范围内
        alpha_mask = np.clip(alpha_mask, 0, 255).astype(np.uint8)

        # ==================== 步骤 4: 白色溢出去除（颜色校正）====================

        if remove_spill:
            # 找出边缘和半透明区域
            semi_transparent = (alpha_mask > 10) & (alpha_mask < 245)

            # 在这些区域增强饱和度（去除过度的灰白色）
            img_float = img.astype(np.float32)

            # 将 BGR 转换为 HSV 进行饱和度调整
            img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)

            # 在半透明区域轻微增强饱和度（去除白色/灰色溢出）
            saturation_boost = 1.2  # 增加 20% 饱和度
            img_hsv[:, :, 1] = np.where(semi_transparent,
                                       np.clip(img_hsv[:, :, 1] * saturation_boost, 0, 255),
                                       img_hsv[:, :, 1])

            # 转换回 BGR
            img = cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        # ==================== 步骤 5: 生成最终图像 ====================

        # 转换 BGR 为 RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 添加 alpha 通道
        img_rgba = np.dstack((img_rgb, alpha_mask))

        # 转换为 PIL 图像
        result_img = PILImage.fromarray(img_rgba, 'RGBA')

        # ==================== 步骤 6: 裁剪透明边缘 ====================

        # 找到非透明像素的边界框
        # 获取所有非完全透明的像素位置（alpha > 0）
        non_transparent = np.where(alpha_mask > 0)

        if len(non_transparent[0]) > 0:
            # 计算边界框
            y_min, y_max = non_transparent[0].min(), non_transparent[0].max()
            x_min, x_max = non_transparent[1].min(), non_transparent[1].max()

            # 裁剪图像到边界框（保留内容，去除纯透明区域）
            result_img = result_img.crop((x_min, y_min, x_max + 1, y_max + 1))

            pixels_removed = int(np.sum(alpha_mask < 128))
            original_size = f"{width}x{height}"
            cropped_size = f"{x_max - x_min + 1}x{y_max - y_min + 1}"

            logger.info(f"         裁剪透明边缘: {original_size} → {cropped_size}")
        else:
            # 图像完全透明，保持原样
            pixels_removed = height * width

        # ==================== 步骤 7: 保存结果 ====================

        # 保存结果
        if overwrite:
            result_img.save(filepath, 'PNG')
        else:
            from pathlib import Path
            path_obj = Path(filepath)
            nobg_path = path_obj.parent / f"{path_obj.stem}_nobg{path_obj.suffix}"
            result_img.save(str(nobg_path), 'PNG')

        return True, pixels_removed

    except Exception as e:
        logger.error(f"         GrabCut 背景移除失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def remove_background(filepath, name, skip_backgrounds=True, overwrite=True,
                      tolerance=40, threshold=200, category=None,
                      algorithm="grabcut", **kwargs):
    """
    移除背景（调度器）

    根据配置选择使用简单算法或 GrabCut 算法

    Args:
        filepath: 图像文件路径
        name: 素材名称
        skip_backgrounds: 是否跳过背景/插画素材
        overwrite: 是否覆盖原文件
        tolerance: 颜色容差（0-100）
        threshold: 白色阈值（0-255）
        category: 素材分类
        algorithm: 算法选择 ("simple" 或 "grabcut")
        **kwargs: 额外参数（传递给具体算法）

    Returns:
        tuple: (是否成功, 处理的像素数)
    """
    if algorithm == "grabcut":
        return remove_white_background_grabcut(
            filepath, name, skip_backgrounds, overwrite,
            tolerance, threshold, category,
            iterations=kwargs.get('grabcut_iterations', 5),
            edge_feather=kwargs.get('edge_feather', 3),
            remove_spill=kwargs.get('remove_color_spill', True),
            auto_detect=kwargs.get('auto_detect_background', True)
        )
    else:  # algorithm == "simple"
        return remove_white_background_simple(
            filepath, name, skip_backgrounds, overwrite,
            tolerance, threshold, category
        )


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

    logger.info(f"开始生成 {len(tasks)} 张图像...")
    logger.info(f"默认美术风格: {ART_STYLE}（可由任务参数覆盖）")
    logger.info(f"自动移除背景: {'开启' if AUTO_REMOVE_BACKGROUND else '关闭'}")
    logger.info(f"输出目录: {full_output_dir}")
    logger.info("="*80)

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
                need_white_background=task.get("need_white_background", True)
            )
        else:
            error_msg = f"缺少 prompt 或 description"
            logger.warning(f"[{idx}/{len(tasks)}] 跳过 {name} - {error_msg}")
            errors.append({"name": name, "error": error_msg})
            fail_count += 1
            continue

        if not prompt:
            error_msg = f"无效的提示词"
            logger.warning(f"[{idx}/{len(tasks)}] 跳过 {name} - {error_msg}")
            errors.append({"name": name, "error": error_msg})
            fail_count += 1
            continue

        # 获取目标图像尺寸
        target_size = task.get("size", "1024x1024")

        # 获取模型名称
        model_name = MODEL_NAME

        # 计算最佳 API 尺寸（根据模型自动适配）
        api_size, scale_factor, need_resize = calculate_api_size(target_size, model_name)

        logger.info(f"\n[{idx}/{len(tasks)}] 正在生成: {name}")
        logger.info(f"使用模型: {model_name}")
        logger.info(f"使用风格: {actual_style}")
        logger.info(f"目标尺寸: {target_size}")
        logger.info(f"API 生成尺寸: {api_size}")
        if need_resize:
            logger.info(f"缩放策略: {api_size} → {target_size} (缩放因子: {scale_factor:.2f}x)")
        else:
            logger.info(f"缩放策略: 直接使用目标尺寸，无需后处理")
        logger.info(f"提示词: {prompt[:100]}..." if len(prompt) > 100 else f"提示词: {prompt}")

        try:
            # 调用豆包图像生成 API（使用智能计算的尺寸和指定模型）
            imagesResponse = client.images.generate(
                model=model_name,
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

                logger.info(f"成功保存: {filename}")

                # 自动移除背景
                background_removed = False
                pixels_removed = 0
                if AUTO_REMOVE_BACKGROUND:
                    algorithm = BACKGROUND_REMOVAL_CONFIG.get("algorithm", "grabcut")
                    logger.info(f"移除背景中 (算法: {algorithm})...")
                    background_removed, pixels_removed = remove_background(
                        filename,
                        name,
                        BACKGROUND_REMOVAL_CONFIG["skip_backgrounds"],
                        BACKGROUND_REMOVAL_CONFIG["overwrite"],
                        BACKGROUND_REMOVAL_CONFIG["tolerance"],
                        BACKGROUND_REMOVAL_CONFIG["threshold"],
                        task.get("category"),  # 传递 category 参数用于判断背景图
                        algorithm=algorithm,
                        grabcut_iterations=BACKGROUND_REMOVAL_CONFIG.get("grabcut_iterations", 5),
                        edge_feather=BACKGROUND_REMOVAL_CONFIG.get("edge_feather", 1),
                        remove_color_spill=BACKGROUND_REMOVAL_CONFIG.get("remove_color_spill", True),
                        auto_detect_background=BACKGROUND_REMOVAL_CONFIG.get("auto_detect_background", True),
                        use_edge_detection=BACKGROUND_REMOVAL_CONFIG.get("use_edge_detection", True)
                    )
                    if background_removed and pixels_removed > 0:
                        logger.info(f"背景已移除 (处理了 {pixels_removed:,} 个像素)")
                    elif background_removed and pixels_removed == 0:
                        logger.info(f"未检测到白色背景")
                    else:
                        # background_removed == False 说明跳过了（background 或 illustration）
                        logger.info(f"跳过抠图（背景/插画类素材）")

                # 缩放图像到目标尺寸（保持比例）
                resized = False
                original_size = None
                final_size = None
                if need_resize:
                    logger.info(f"缩放图像: {api_size} → {target_size} (保持比例)...")
                    resized, original_size, final_size = resize_image(filename, target_size, name, keep_aspect_ratio=True)
                    if resized:
                        logger.info(f"图像已缩放: {original_size} → {final_size}")
                    else:
                        logger.error(f"图像缩放失败")
                else:
                    logger.info(f"尺寸已匹配，跳过缩放")
                    resized = True
                    # 获取当前图像尺寸（可能已经被裁剪）
                    current_img = PILImage.open(filename)
                    original_size = current_img.size
                    final_size = current_img.size

                # 记录图像信息（仅用于返回值）
                images_info.append({
                    "filename": f"{name}.png",
                    "name": name,
                    "prompt": prompt,
                    "style": actual_style,
                    "target_size": target_size,
                    "api_size": api_size,
                    "scale_factor": scale_factor,
                    "background_removed": background_removed,
                    "pixels_removed": pixels_removed,
                    "resized": need_resize,
                    "original_size": f"{original_size[0]}x{original_size[1]}" if original_size else None,
                    "final_size": f"{final_size[0]}x{final_size[1]}" if final_size else None
                })

                success_count += 1

            else:
                error_msg = f"图片下载失败，状态码: {response.status_code}"
                logger.error(f"{error_msg}")
                errors.append({"name": name, "error": error_msg})
                fail_count += 1

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"生成失败: {error_msg}")
            errors.append({"name": name, "error": error_msg})
            fail_count += 1

    # 输出统计信息
    logger.info("\n" + "="*80)
    logger.info(f"生成完成！")
    logger.info(f"成功: {success_count} 个")
    logger.info(f"失败: {fail_count} 个")
    logger.info(f"保存位置: {full_output_dir}/")

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


# ==================== 测试模式函数 ====================

def test_process_local_images():
    """
    测试模式：处理本地目录下的图像（不调用API）
    """
    import glob
    from pathlib import Path

    input_dir = TEST_MODE.get("input_directory", "./input-images")
    output_dir = TEST_MODE.get("output_directory", "./processed-images")
    target_size = TEST_MODE.get("target_size")

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 查找所有图像文件
    image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(input_dir, ext)))
        image_files.extend(glob.glob(os.path.join(input_dir, ext.upper())))

    if not image_files:
        logger.error(f"未在 {input_dir} 目录下找到任何图像文件")
        return

    logger.info(f"测试模式 - 本地图像处理")
    logger.info(f"输入目录: {input_dir}")
    logger.info(f"找到 {len(image_files)} 张图像")
    logger.info(f"自动移除背景: {'开启' if AUTO_REMOVE_BACKGROUND else '关闭'}")
    logger.info(f"目标尺寸: {target_size if target_size else '保持原尺寸'}")
    logger.info(f"输出目录: {output_dir}")
    logger.info("="*80)

    success_count = 0
    fail_count = 0

    for idx, filepath in enumerate(image_files, 1):
        path_obj = Path(filepath)
        name = path_obj.stem
        extension = path_obj.suffix

        logger.info(f"\n[{idx}/{len(image_files)}] 正在处理: {name}{extension}")

        try:
            # 复制到输出目录（转换为PNG）
            output_filepath = os.path.join(output_dir, f"{name}.png")
            img = PILImage.open(filepath)
            original_size = img.size
            img.save(output_filepath, 'PNG')
            logger.info(f"已复制: {output_filepath}")

            # 自动移除背景
            if AUTO_REMOVE_BACKGROUND:
                algorithm = BACKGROUND_REMOVAL_CONFIG.get("algorithm", "grabcut")
                logger.info(f"移除背景中 (算法: {algorithm})...")
                background_removed, pixels_removed = remove_background(
                    output_filepath,
                    name,
                    BACKGROUND_REMOVAL_CONFIG["skip_backgrounds"],
                    BACKGROUND_REMOVAL_CONFIG["overwrite"],
                    BACKGROUND_REMOVAL_CONFIG["tolerance"],
                    BACKGROUND_REMOVAL_CONFIG["threshold"],
                    None,  # category 未知
                    algorithm=algorithm,
                    grabcut_iterations=BACKGROUND_REMOVAL_CONFIG.get("grabcut_iterations", 5),
                    edge_feather=BACKGROUND_REMOVAL_CONFIG.get("edge_feather", 1),
                    remove_color_spill=BACKGROUND_REMOVAL_CONFIG.get("remove_color_spill", True),
                    auto_detect_background=BACKGROUND_REMOVAL_CONFIG.get("auto_detect_background", True),
                    use_edge_detection=BACKGROUND_REMOVAL_CONFIG.get("use_edge_detection", True)
                )
                if background_removed and pixels_removed > 0:
                    logger.info(f"背景已移除 (处理了 {pixels_removed:,} 个像素)")
                elif background_removed and pixels_removed == 0:
                    logger.info(f"未检测到背景")
                else:
                    logger.info(f"跳过抠图")

            # 缩放到目标尺寸（如果指定）
            if target_size:
                logger.info(f"缩放图像到目标尺寸: {target_size}...")
                resized, _, final_size = resize_image(output_filepath, target_size, name, keep_aspect_ratio=True)
                if resized:
                    logger.info(f"图像已缩放: {original_size} → {final_size}")
                else:
                    logger.error(f"图像缩放失败")

            success_count += 1

        except Exception as e:
            logger.error(f"处理失败: {type(e).__name__}: {e}")
            fail_count += 1

    # 输出统计
    logger.info("\n" + "="*80)
    logger.info(f"处理完成！")
    logger.info(f"成功: {success_count} 个")
    logger.info(f"失败: {fail_count} 个")
    logger.info(f"保存位置: {output_dir}/")


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    # 检查是否为测试模式
    if TEST_MODE.get("enabled", False):
        # 测试模式
        if TEST_MODE.get("use_api", False):
            # 使用API生成图像
            tasks_config = TEST_MODE.get("tasks_config", "tasks.json")
            tasks = load_tasks(tasks_config)

            if tasks:
                output_dir = TEST_MODE.get("output_directory", "./generated-images")
                generate_images(tasks, output_dir=output_dir)
            else:
                logger.error(f"错误: 无法从 {tasks_config} 加载任务！")
        else:
            # 处理本地图像
            test_process_local_images()
    else:
        # 正常模式：从配置文件加载任务并调用API生成
        tasks = load_tasks("tasks.json")

        if tasks:
            generate_images(tasks)
        else:
            logger.error("错误: 没有可执行的任务！")
            logger.info("请检查 tasks.json 文件并添加任务。")
