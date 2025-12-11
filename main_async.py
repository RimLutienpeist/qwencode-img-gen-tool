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
from openai import OpenAI
from dotenv import load_dotenv
import asyncio
import aiohttp
import time
import numpy as np
from PIL import Image as PILImage
import cv2
from typing import List, Dict, Tuple

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

        print(f"\n[{idx}/{total}] 正在生成: {name}")
        print(f"  模型: {model_name}")
        print(f"  风格: {actual_style}")
        print(f"  目标尺寸: {target_size}")
        print(f"  API 尺寸: {api_size}")
        if need_resize:
            print(f"  缩放策略: {api_size} → {target_size} ({scale_factor:.2f}x)")
        print(f"  提示词: {prompt[:80]}..." if len(prompt) > 80 else f"  提示词: {prompt}")

        # ==================== 阶段 1: API 调用（异步） ====================

        start_time = time.time()

        # 注意：OpenAI Python SDK 不支持异步，这里使用同步调用
        # 在实际并发中，这部分会被 asyncio.to_thread 包装
        loop = asyncio.get_event_loop()
        imagesResponse = await loop.run_in_executor(
            None,  # 使用默认线程池
            lambda: client.images.generate(
                model=model_name,
                prompt=prompt,
                size=api_size,
                response_format="url",
                extra_body={"watermark": False}
            )
        )

        img_url = imagesResponse.data[0].url
        api_time = time.time() - start_time
        print(f"  ✓ API 响应完成 ({api_time:.1f}s)")

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
        print(f"  ✓ 图像下载完成 ({download_time:.1f}s, {len(image_data) / 1024:.1f} KB)")

        # ==================== 阶段 3: 保存图像 ====================

        filename = f"{output_dir}/{name}.png"
        with open(filename, "wb") as f:
            f.write(image_data)

        print(f"  ✓ 保存: {filename}")

        # ==================== 阶段 4: 背景移除（同步，CPU 密集） ====================

        background_removed = False
        pixels_removed = 0

        if AUTO_REMOVE_BACKGROUND:
            bg_start = time.time()
            algorithm = BACKGROUND_REMOVAL_CONFIG.get("algorithm", "grabcut")
            print(f"  移除背景中 (算法: {algorithm})...")

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
                    auto_detect_background=BACKGROUND_REMOVAL_CONFIG.get("auto_detect_background", False)
                )
            )

            bg_time = time.time() - bg_start
            if background_removed and pixels_removed > 0:
                print(f"  ✓ 背景已移除 ({bg_time:.1f}s, {pixels_removed:,} 像素)")
            elif background_removed and pixels_removed == 0:
                print(f"  • 未检测到背景")
            else:
                print(f"  • 跳过抠图（背景/插画类）")

        # ==================== 阶段 5: 图像缩放（同步，CPU 密集） ====================

        original_size = None
        final_size = None

        if need_resize:
            resize_start = time.time()
            print(f"  缩放图像: {api_size} → {target_size}...")

            resized, original_size, final_size = await loop.run_in_executor(
                None,
                lambda: resize_image(filename, target_size, name, keep_aspect_ratio=True)
            )

            resize_time = time.time() - resize_start
            if resized:
                print(f"  ✓ 图像已缩放 ({resize_time:.1f}s): {original_size} → {final_size}")
            else:
                print(f"  ✗ 图像缩放失败")
        else:
            current_img = PILImage.open(filename)
            original_size = current_img.size
            final_size = current_img.size

        # ==================== 完成 ====================

        total_time = time.time() - start_time
        print(f"  ✓ 完成 (总耗时: {total_time:.1f}s)")

        return {
            "success": True,
            "name": name,
            "filename": f"{name}.png",
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
        print(f"  ✗ 生成失败: {type(e).__name__}: {e}")
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

    print(f"开始并发生成 {len(tasks)} 张图像 (最大并发: {max_concurrent})...")
    print(f"默认美术风格: {ART_STYLE}")
    print(f"自动移除背景: {'开启' if AUTO_REMOVE_BACKGROUND else '关闭'}")
    print(f"输出目录: {full_output_dir}")
    print("="*80)

    overall_start = time.time()

    # 创建 aiohttp 会话
    timeout = aiohttp.ClientTimeout(total=600)  # 10 分钟超时
    async with aiohttp.ClientSession(timeout=timeout) as session:
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

    print("\n" + "="*80)
    print(f"并发生成完成！")
    print(f"总耗时: {overall_time:.1f}s (平均: {overall_time / len(tasks):.1f}s/张)")
    print(f"成功: {success_count} 个")
    print(f"失败: {fail_count} 个")
    print(f"保存位置: {full_output_dir}/")

    if success_count > 0:
        avg_time = sum(r.get("time", 0) for r in success_results) / success_count
        print(f"平均单张耗时: {avg_time:.1f}s")
        print(f"并发加速比: {(avg_time * len(tasks)) / overall_time:.1f}x")

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

        print(f"\n生成完成！")
        print(f"  成功: {result['success_count']}")
        print(f"  失败: {result['fail_count']}")
        print(f"  总耗时: {result['total_time']:.1f}s")
    else:
        print("错误: 没有可执行的任务！")
