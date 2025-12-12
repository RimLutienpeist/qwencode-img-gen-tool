"""
游戏素材图像生成工具 - 异步并发版本

相比串行版本的优势：
1. API 调用并发：同时发送多个图像生成请求
2. 下载并发：并行下载生成的图像
3. 处理串行：保持图像处理部分串行（避免 CPU 过载）

性能提升：
- 3张图像：串行 30-90秒 → 并发 15-35秒（约快 2x）
- 5张图像：串行 50-150秒 → 并发 20-50秒（约快 2-3x）
- 10张图像：串行 100-300秒 → 并发 30-80秒（约快 3-4x）
"""

import os
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv
import asyncio
import aiohttp
import time
import numpy as np
from PIL import Image as PILImage
import cv2
from typing import List, Dict, Tuple

# 配置日志
logging.disable(logging.CRITICAL)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从原 main.py 导入所有函数和配置
import main

load_dotenv()

# 使用原有的配置
client = main.client
MODEL_NAME = main.MODEL_NAME
ART_STYLE = main.ART_STYLE
AUTO_REMOVE_BACKGROUND = main.AUTO_REMOVE_BACKGROUND
BACKGROUND_REMOVAL_CONFIG = main.BACKGROUND_REMOVAL_CONFIG
SYSTEM_PROMPTS = main.SYSTEM_PROMPTS
MODEL_SIZE_RANGES = main.MODEL_SIZE_RANGES

# 复用原有函数
build_prompt = main.build_prompt
calculate_api_size = main.calculate_api_size
resize_image = main.resize_image
remove_background = main.remove_background
extract_difference = main.extract_difference  # 新增：差分提取函数


# ==================== 异步生成单张图像 ====================

async def generate_single_image_async(
    session: aiohttp.ClientSession,
    task: Dict,
    idx: int,
    total: int,
    output_dir: str
) -> Dict:
    """
    异步生成单张图像

    Args:
        session: aiohttp 会话
        task: 任务配置
        idx: 任务索引
        total: 总任务数
        output_dir: 输出目录

    Returns:
        dict: 生成结果
    """
    name = task["name"]
    viewpoint = task.get("viewpoint")  # 获取视角参数

    try:
        # 构建提示词
        if "prompt" in task:
            prompt = task["prompt"]
            actual_style = task.get("style", ART_STYLE)
        elif "description" in task:
            actual_style = task.get("style", ART_STYLE)
            prompt = build_prompt(
                description=task["description"],
                category=task.get("category"),
                style=actual_style,
                viewpoint=viewpoint,  # 传入视角参数
                need_white_background=task.get("need_white_background", True)
            )
        else:
            return {
                "success": False,
                "name": name,
                "error": "缺少 prompt 或 description"
            }

        # 获取目标尺寸
        target_size = task.get("size", "1024x1024")
        model_name = MODEL_NAME

        # 计算最佳 API 尺寸
        api_size, scale_factor, need_resize = calculate_api_size(target_size, model_name)

        # 构建文件名（如果有视角，加入文件名）
        if viewpoint:
            final_name = f"{name}_{viewpoint}"
            logger.info(f"\n[{idx}/{total}] 正在生成: {name} (视角: {viewpoint})")
        else:
            final_name = name
            logger.info(f"\n[{idx}/{total}] 正在生成: {name}")

        logger.info(f"  模型: {model_name}")
        logger.info(f"  风格: {actual_style}")
        logger.info(f"  目标尺寸: {target_size}")
        logger.info(f"  API 尺寸: {api_size}")
        if need_resize:
            logger.info(f"  缩放策略: {api_size} → {target_size} ({scale_factor:.2f}x)")
        logger.info(f"  提示词: {prompt[:80]}..." if len(prompt) > 80 else f"  提示词: {prompt}")

        # ==================== 检查是否为图生图模式 ====================

        reference_image = task.get("reference_image")  # 参考图像路径或名称
        use_difference_extraction = task.get("extract_difference", False)  # 是否使用差分提取

        # 如果指定了reference_image，构建完整路径
        reference_image_path = None
        if reference_image:
            # 如果是相对路径或仅文件名，在output_dir中查找
            if not os.path.isabs(reference_image):
                reference_image_path = os.path.join(output_dir, reference_image)
                # 如果没有扩展名，添加.png
                if not reference_image_path.endswith(('.png', '.jpg', '.jpeg')):
                    reference_image_path += '.png'
            else:
                reference_image_path = reference_image

            # 检查文件是否存在
            if not os.path.exists(reference_image_path):
                return {
                    "success": False,
                    "name": name,
                    "error": f"参考图像不存在: {reference_image_path}"
                }

            logger.info(f"  图生图模式: 参考图像 = {reference_image_path}")
            if use_difference_extraction:
                logger.info(f"  将使用差分提取提取新增内容")

        # ==================== 阶段 1: API 调用（异步） ====================

        start_time = time.time()

        # 准备API参数
        api_params = {
            "model": model_name,
            "prompt": prompt,
            "size": api_size,
            "response_format": "url",
            "extra_body": {"watermark": False}
        }

        # 如果有参考图像，添加image参数
        if reference_image_path:
            # 读取并编码图像为base64，然后转换为data URL
            import base64
            with open(reference_image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            # 豆包API可能需要data URL格式: data:image/png;base64,<base64_data>
            data_url = f"data:image/png;base64,{image_data}"
            api_params["extra_body"]["image"] = data_url

        # 注意：OpenAI Python SDK 不支持异步，这里使用同步调用
        # 在实际并发中，这部分会被 asyncio.to_thread 包装
        loop = asyncio.get_event_loop()
        imagesResponse = await loop.run_in_executor(
            None,  # 使用默认线程池
            lambda: client.images.generate(**api_params)
        )

        img_url = imagesResponse.data[0].url
        api_time = time.time() - start_time
        logger.info(f"  ✓ API 响应完成 ({api_time:.1f}s)")

        # ==================== 阶段 2: 图像下载（异步） ====================

        download_start = time.time()
        async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=60)) as response:
            if response.status != 200:
                return {
                    "success": False,
                    "name": name,
                    "error": f"下载失败，状态码: {response.status}"
                }

            image_data = await response.read()

        download_time = time.time() - download_start
        logger.info(f"  ✓ 图像下载完成 ({download_time:.1f}s, {len(image_data) / 1024:.1f} KB)")

        # ==================== 阶段 3: 保存图像 ====================

        filename = f"{output_dir}/{final_name}.png"

        # 如果使用差分提取，先保存为临时文件
        if use_difference_extraction and reference_image_path:
            temp_filename = f"{output_dir}/{final_name}_composite_temp.png"
            with open(temp_filename, "wb") as f:
                f.write(image_data)
            logger.info(f"  ✓ 临时保存合成图: {temp_filename}")

            # 执行差分提取（在线程池中执行，避免阻塞）
            logger.info(f"  差分提取中...")
            extracted, num_regions = await loop.run_in_executor(
                None,
                lambda: extract_difference(
                    base_image_path=reference_image_path,
                    composite_image_path=temp_filename,
                    output_path=filename,
                    name=name,
                    sensitivity=task.get("diff_sensitivity", 30),
                    min_area=task.get("diff_min_area", 100),
                    edge_feather=task.get("diff_edge_feather", 2)
                )
            )

            if extracted:
                logger.info(f"  ✓ 差分提取成功: 提取了 {num_regions} 个区域")
                # 删除临时文件
                os.remove(temp_filename)
            else:
                # 如果差分提取失败，保留合成图
                logger.warning(f"  ⚠ 差分提取失败，保留合成图")
                os.rename(temp_filename, filename)

        else:
            # 普通模式，直接保存
            with open(filename, "wb") as f:
                f.write(image_data)

        logger.info(f"  ✓ 保存: {filename}")

        # ==================== 阶段 4: 背景移除（同步，CPU 密集） ====================

        background_removed = False
        pixels_removed = 0

        # 如果使用了差分提取，通常不需要再移除背景（已经是透明背景）
        if AUTO_REMOVE_BACKGROUND and not use_difference_extraction:
            bg_start = time.time()
            algorithm = BACKGROUND_REMOVAL_CONFIG.get("algorithm", "grabcut")
            logger.info(f"  移除背景中 (算法: {algorithm})...")

            # 在线程池中执行（避免阻塞事件循环）
            background_removed, pixels_removed = await loop.run_in_executor(
                None,
                lambda: remove_background(
                    filename,
                    name,
                    BACKGROUND_REMOVAL_CONFIG["skip_backgrounds"],
                    BACKGROUND_REMOVAL_CONFIG["overwrite"],
                    BACKGROUND_REMOVAL_CONFIG["tolerance"],
                    BACKGROUND_REMOVAL_CONFIG["threshold"],
                    task.get("category"),
                    algorithm=algorithm,
                    grabcut_iterations=BACKGROUND_REMOVAL_CONFIG.get("grabcut_iterations", 5),
                    edge_feather=BACKGROUND_REMOVAL_CONFIG.get("edge_feather", 1),
                    remove_color_spill=BACKGROUND_REMOVAL_CONFIG.get("remove_color_spill", True),
                    auto_detect_background=BACKGROUND_REMOVAL_CONFIG.get("auto_detect_background", True),
                    use_edge_detection=BACKGROUND_REMOVAL_CONFIG.get("use_edge_detection", True)
                )
            )

            bg_time = time.time() - bg_start
            if background_removed and pixels_removed > 0:
                logger.info(f"  ✓ 背景已移除 ({bg_time:.1f}s, {pixels_removed:,} 像素)")
            elif background_removed and pixels_removed == 0:
                logger.info(f"  • 未检测到背景")
            else:
                logger.info(f"  • 跳过抠图（背景/插画类）")

        # ==================== 阶段 5: 图像缩放（同步，CPU 密集） ====================

        skip_resize = task.get("skip_resize", False)
        original_size = None
        final_size = None

        if skip_resize:
            # 图生图素材，跳过resize
            logger.info(f"  • 图生图素材，跳过resize步骤")
            current_img = PILImage.open(filename)
            original_size = current_img.size
            final_size = current_img.size
        elif need_resize:
            resize_start = time.time()
            logger.info(f"  缩放图像: {api_size} → {target_size}...")

            resized, original_size, final_size = await loop.run_in_executor(
                None,
                lambda: resize_image(filename, target_size, name, keep_aspect_ratio=True)
            )

            resize_time = time.time() - resize_start
            if resized:
                logger.info(f"  ✓ 图像已缩放 ({resize_time:.1f}s): {original_size} → {final_size}")
            else:
                logger.error(f"  ✗ 图像缩放失败")
        else:
            current_img = PILImage.open(filename)
            original_size = current_img.size
            final_size = current_img.size

        # ==================== 完成 ====================

        total_time = time.time() - start_time
        logger.info(f"  ✓ 完成 (总耗时: {total_time:.1f}s)")

        return {
            "success": True,
            "name": name,
            "filename": f"{final_name}.png",
            "viewpoint": viewpoint,  # 添加视角信息
            "prompt": prompt,
            "style": actual_style,
            "target_size": target_size,
            "api_size": api_size,
            "scale_factor": scale_factor,
            "background_removed": background_removed,
            "pixels_removed": pixels_removed,
            "resized": need_resize,
            "original_size": f"{original_size[0]}x{original_size[1]}" if original_size else None,
            "final_size": f"{final_size[0]}x{final_size[1]}" if final_size else None,
            "time": total_time
        }

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"  ✗ 生成失败: {type(e).__name__}: {e}")
        return {
            "success": False,
            "name": name,
            "error": f"{type(e).__name__}: {e}",
            "error_detail": error_detail
        }


# ==================== 并发生成多张图像 ====================

async def generate_images_async(tasks: List[Dict], output_dir: str = "./generated-images", max_concurrent: int = 5) -> Dict:
    """
    并发批量生成图像

    Args:
        tasks: 任务列表
        output_dir: 输出目录
        max_concurrent: 最大并发数（建议 3-5，避免 API 限流）

    Returns:
        dict: 生成结果报告
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    full_output_dir = output_dir

    logger.info(f"开始并发生成 {len(tasks)} 张图像 (最大并发: {max_concurrent})...")
    logger.info(f"默认美术风格: {ART_STYLE}")
    logger.info(f"自动移除背景: {'开启' if AUTO_REMOVE_BACKGROUND else '关闭'}")
    logger.info(f"输出目录: {full_output_dir}")
    logger.info("="*80)

    overall_start = time.time()

    # ==================== 智能任务调度：背景图优先 ====================
    # 检查是否有图生图任务（reference_image 不为空）
    has_img2img = any(task.get("reference_image") for task in tasks)

    if has_img2img:
        logger.info("检测到图生图任务，启用两阶段生成...")
        logger.info("  阶段1: 串行生成背景图（作为参考图像）")
        logger.info("  阶段2: 并发生成其他素材（基于背景图）")
        logger.info("="*80)

    # 创建 aiohttp 会话
    timeout = aiohttp.ClientTimeout(total=600)  # 10 分钟超时
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = []

        if has_img2img:
            # ==================== 阶段 1: 串行生成背景图 ====================
            background_tasks = []
            img2img_tasks = []

            for idx, task in enumerate(tasks, 1):
                if task.get("reference_image"):
                    # 需要参考图像的任务，放入第二阶段
                    img2img_tasks.append((task, idx))
                else:
                    # 不需要参考图像的任务（通常是背景图），放入第一阶段
                    background_tasks.append((task, idx))

            # 串行生成背景图（确保参考图像存在）
            logger.info(f"\n[阶段1] 串行生成 {len(background_tasks)} 个背景图...")
            for task, idx in background_tasks:
                result = await generate_single_image_async(session, task, idx, len(tasks), full_output_dir)
                results.append(result)

            logger.info(f"\n✓ 阶段1完成，背景图已生成")
            logger.info("="*80)

            # ==================== 阶段 2: 并发生成图生图素材 ====================
            logger.info(f"\n[阶段2] 并发生成 {len(img2img_tasks)} 个图生图素材...")

            # 使用信号量控制并发数
            semaphore = asyncio.Semaphore(max_concurrent)

            async def bounded_generate(task: Dict, idx: int) -> Dict:
                """带并发控制的生成函数"""
                async with semaphore:
                    return await generate_single_image_async(session, task, idx, len(tasks), full_output_dir)

            # 并发执行图生图任务
            img2img_results = await asyncio.gather(
                *[bounded_generate(task, idx) for task, idx in img2img_tasks],
                return_exceptions=True
            )
            results.extend(img2img_results)

        else:
            # ==================== 普通模式：全部并发 ====================
            # 使用信号量控制并发数
            semaphore = asyncio.Semaphore(max_concurrent)

            async def bounded_generate(task: Dict, idx: int) -> Dict:
                """带并发控制的生成函数"""
                async with semaphore:
                    return await generate_single_image_async(session, task, idx, len(tasks), full_output_dir)

            # 并发执行所有任务
            results = await asyncio.gather(
                *[bounded_generate(task, idx) for idx, task in enumerate(tasks, 1)],
                return_exceptions=True
            )

    # ==================== 统计结果 ====================

    overall_time = time.time() - overall_start

    success_results = [r for r in results if isinstance(r, dict) and r.get("success")]
    failed_results = [r for r in results if isinstance(r, dict) and not r.get("success")]
    exception_results = [r for r in results if isinstance(r, Exception)]

    success_count = len(success_results)
    fail_count = len(failed_results) + len(exception_results)

    # 错误信息
    errors = []
    for r in failed_results:
        errors.append({"name": r.get("name", "未知"), "error": r.get("error", "未知错误")})
    for e in exception_results:
        errors.append({"name": "未知", "error": f"异常: {e}"})

    # 图像信息
    images_info = [r for r in success_results]

    # ==================== 输出统计 ====================

    logger.info("\n" + "="*80)
    logger.info(f"并发生成完成！")
    logger.info(f"总耗时: {overall_time:.1f}s (平均: {overall_time / len(tasks):.1f}s/张)")
    logger.info(f"成功: {success_count} 个")
    logger.info(f"失败: {fail_count} 个")
    logger.info(f"保存位置: {full_output_dir}/")

    if success_count > 0:
        avg_time = sum(r.get("time", 0) for r in success_results) / success_count
        logger.info(f"平均单张耗时: {avg_time:.1f}s")
        logger.info(f"并发加速比: {(avg_time * len(tasks)) / overall_time:.1f}x")

    return {
        "success": success_count > 0,
        "success_count": success_count,
        "fail_count": fail_count,
        "output_dir": full_output_dir,
        "images": images_info,
        "errors": errors,
        "total": len(tasks),
        "total_time": overall_time,
        "avg_time_per_image": overall_time / len(tasks) if len(tasks) > 0 else 0
    }


# ==================== 同步包装函数（供 MCP 使用） ====================

def generate_images_concurrent(tasks: List[Dict], output_dir: str = "./generated-images", max_concurrent: int = 5) -> Dict:
    """
    同步接口的并发生成函数（供 MCP 服务器调用）

    自动检测是否已有运行中的事件循环：
    - 如果有：在新线程中运行新的事件循环
    - 如果没有：创建新的事件循环（使用 asyncio.run）

    Args:
        tasks: 任务列表
        output_dir: 输出目录
        max_concurrent: 最大并发数

    Returns:
        dict: 生成结果
    """
    try:
        # 尝试获取当前运行中的事件循环
        loop = asyncio.get_running_loop()

        # 如果成功获取到循环，说明已经在异步环境中
        # 需要在新线程中运行新的事件循环
        import concurrent.futures
        import threading

        def run_in_new_loop():
            # 在新线程中创建新的事件循环
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(
                    generate_images_async(tasks, output_dir, max_concurrent)
                )
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            return future.result()

    except RuntimeError:
        # 没有运行中的事件循环，使用 asyncio.run()
        return asyncio.run(generate_images_async(tasks, output_dir, max_concurrent))


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    # 从配置文件加载任务
    tasks = main.load_tasks("tasks.json")

    if tasks:
        # 使用并发版本
        result = generate_images_concurrent(tasks, max_concurrent=5)

        logger.info(f"\n生成完成！")
        logger.info(f"  成功: {result['success_count']}")
        logger.info(f"  失败: {result['fail_count']}")
        logger.info(f"  总耗时: {result['total_time']:.1f}s")
    else:
        logger.error("错误: 没有可执行的任务！")
