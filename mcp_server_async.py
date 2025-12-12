# mcp_server_async.py - 支持并发的 MCP 服务器
import sys
import os
import time
import json
import logging
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.disable(logging.CRITICAL)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 显式添加当前目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 导入异步版本的生成引擎
try:
    import main_async as engine
    import main  # 保留原有的辅助函数
except ImportError as e:
    logger.error(f"错误：无法导入模块 - {e}")
    logger.info("请确保 mcp_server_async.py 和 main_async.py 在同一目录下")
    sys.exit(1)

# 初始化 MCP 服务器
mcp = FastMCP("DoubaoAssetGenerator-Async")

@mcp.tool()
def generate_game_asset(workspace_dir: str) -> str:
    """
    Reads the task list from tasks.json and concurrently batch-generates game asset images, with intelligent background removal.

    Core Functions:
    1. Read the task list from the workspace_dir/public/tasks.json file.
    2. Concurrently generate multiple images (Save to workspace_dir/public/assets/).
    3. Automatically identify and remove the background, exporting transparent PNGs (Background removal is conditional on the category).
    4. Reset tasks.json to an empty template after generation is complete.
    5. **AUTO Image-to-Image**: First background image is used as reference for all other assets (automatic matching of size and style).

    Background Processing Rules:
    - 'background' and 'illustration' categories: Keep the original background (No removal).
    - Other categories (Character, UI, Prop, etc.): Automatically detect and remove the background color.

    Intelligent Size Optimization:
    - Supports arbitrary sizes (e.g., 128x128, 1024x1024, 4096x4096).

    Auto Image-to-Image Workflow:
    - First task with category='background': Generated normally (reference image).
    - All subsequent non-background tasks: Automatically use the background as reference + difference extraction + skip resize.
    - Result: All assets match the background's style and size perfectly!

    Args:
        workspace_dir: Path to the working directory of Qwen Code (e.g., "/home/user/phaser-frame-lite").

    tasks.json Format:
    [
        {
        "description": "Image description (Required)",
        "category": "char_portrait|char_sprite|ui_asset|effect|illustration|logo|prop|background",
        "style": "pixel|cartoon|realistic",
        "viewpoint": "Viewpoint description (Optional, preset keywords or custom text)",
        "name": "Filename (without extension)",
        "size": "Width x Height (e.g., 1024x512)"
        }
    ]

    Workflow Example:
    [
      {"description": "Forest scene", "category": "background", "name": "forest_bg", "size": "1920x1080"},
      {"description": "Knight character", "category": "char_sprite", "name": "knight", "size": "1920x1080"},
      {"description": "Treasure chest", "category": "prop", "name": "chest", "size": "1920x1080"}
    ]
    → forest_bg.png (1920x1080, full background)
    → knight.png (auto extracted, transparent background, matching size/style)
    → chest.png (auto extracted, transparent background, matching size/style)

    Category Descriptions:
    - char_portrait: Character portrait (Background removal)
    - char_sprite: Character sprite/game sprite (Background removal)
    - ui_asset: UI component (Background removal)
    - effect: Effect element (Background removal)
    - logo: Logo/Title (Background removal)
    - prop: Prop/Item (Background removal)
    - illustration: Illustration/CG (No background removal)
    - background: Background/Base map (No background removal)

    Style Descriptions:
    - pixel: Pixel style (8bit/16bit retro game style)
    - cartoon: Cartoon style (Comic rendering, bright colors)
    - realistic: Realistic style (3D rendering, high detail)

    Viewpoint Descriptions (Optional):
    - Preset keywords: front|back|side|top|isometric|perspective|three_quarter (expanded to full prompts)
    - Custom text: Any viewpoint description (added directly to prompt)
    - Examples: "front", "low angle shot", "bird's eye view", etc.

    Returns:
        str: Batch generation result report, including success/failure count, time statistics, file list, and error details.
    """
    
    max_concurrent = 5

    try:
        logger.info(f"MCP 工具启动（并发模式）")
        logger.info(f"工作目录: {workspace_dir}")
        logger.info(f"最大并发: {max_concurrent}")

        # 1. 读取 tasks.json 文件
        tasks_json_path = os.path.join(workspace_dir, "public", "tasks.json")

        if not os.path.exists(tasks_json_path):
            return f"任务文件不存在: {tasks_json_path}"

        with open(tasks_json_path, "r", encoding="utf-8") as f:
            tasks_data = json.load(f)

        if not tasks_data or not isinstance(tasks_data, list):
            return f"任务文件格式错误，应该是一个数组"

        # 过滤掉空任务
        valid_tasks = [t for t in tasks_data if t.get("description") and t.get("description").strip()]

        if not valid_tasks:
            return f"ℹ 没有有效的任务需要执行（description 为空）"

        logger.info(f"读取到 {len(valid_tasks)} 个有效任务")

        # 2. 基于工作目录设置输出路径
        assets_dir = os.path.join(workspace_dir, "public", "assets")
        assets_dir = os.path.abspath(assets_dir)
        os.makedirs(assets_dir, exist_ok=True)

        # 3. 转换为 main_async.py 需要的格式，并实现自动图生图工作流
        engine_tasks = []
        background_image_name = None  # 记录背景图的名称

        for idx, task_data in enumerate(valid_tasks, 1):
            description = task_data.get("description", "").strip()
            category = task_data.get("category", "none").strip() or "none"
            style = task_data.get("style", "cartoon").strip() or "cartoon"
            viewpoint = task_data.get("viewpoint", "").strip() or None  # 获取视角参数
            name = task_data.get("name", "").strip()
            size = task_data.get("size", "2048x2048").strip() or "2048x2048"

            # 如果没有提供名字，自动生成
            if not name:
                safe_desc = "".join([c for c in description if c.isalnum()])[:10]
                name = f"auto_{safe_desc}_{int(time.time())}_{idx}"

            # 判断是否需要白色背景
            no_white_background_categories = ["background", "illustration"]
            is_background = category in no_white_background_categories

            # ==================== 自动图生图工作流 ====================
            # 规则：
            # 1. 第一个背景图：正常生成，不使用图生图
            # 2. 后续所有素材：自动引用背景图 + 自动差分提取 + 跳过resize

            reference_image = None
            extract_difference = False
            skip_resize = False  # 新增：是否跳过resize

            # 构建实际的文件名（包含viewpoint后缀）
            actual_filename = f"{name}_{viewpoint}" if viewpoint else name

            if is_background and background_image_name is None:
                # 这是第一个背景图，记录完整文件名（包含viewpoint）
                background_image_name = actual_filename
                logger.info(f"  [{idx}] {actual_filename} - 背景图（基准图像）")
            elif background_image_name is not None and not is_background:
                # 非背景图，且已有背景图，自动启用图生图
                reference_image = background_image_name
                extract_difference = True
                skip_resize = True  # 图生图素材跳过resize
                logger.info(f"  [{idx}] {actual_filename} - 自动图生图模式（基于: {background_image_name}）")

            engine_tasks.append({
                "name": name,
                "description": description,
                "category": category,
                "style": style,
                "viewpoint": viewpoint,
                "reference_image": reference_image,
                "extract_difference": extract_difference,
                "skip_resize": skip_resize,  # 传递跳过resize标志
                "size": size,
                "need_white_background": not is_background
            })

            # 日志中包含视角和图生图信息
            viewpoint_info = f" (视角: {viewpoint})" if viewpoint else ""
            img2img_info = f" [图生图→{reference_image}]" if reference_image else ""
            diff_info = " [差分提取]" if extract_difference else ""
            skip_info = " [跳过resize]" if skip_resize else ""
            logger.info(f"     - {category}/{style}{viewpoint_info}{img2img_info}{diff_info}{skip_info} - {description[:40]}...")


        # 4. 调用主程序生成图像（并发版本）
        result = engine.generate_images_concurrent(
            engine_tasks,
            output_dir=assets_dir,
            max_concurrent=max_concurrent
        )

        # 5. 生成完成后，重置 tasks.json 文件为空模板
        logger.info(f"准备重置任务文件: {tasks_json_path}")
        try:
            template = [
                {
                    "description": "",
                    "category": "",
                    "style": "",
                    "viewpoint": "",
                    "name": "",
                    "size": ""
                }
            ]

            logger.info(f"写入空模板到: {tasks_json_path}")
            with open(tasks_json_path, "w", encoding="utf-8") as f:
                json.dump(template, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 已成功重置任务文件为空模板")

            # 验证写入
            with open(tasks_json_path, "r", encoding="utf-8") as f:
                verify_data = json.load(f)
                logger.info(f"验证: 任务文件现在包含 {len(verify_data)} 个模板项")

        except Exception as clear_error:
            logger.error(f"❌ 重置任务文件失败: {clear_error}")
            import traceback
            logger.error(traceback.format_exc())

        # 6. 构建详细的返回消息
        message = f"🚀 并发生成完成！\n\n"
        message += f"📊 统计信息：\n"
        message += f"  • 成功: {result['success_count']} 个\n"
        message += f"  • 失败: {result['fail_count']} 个\n"
        message += f"  • 总耗时: {result.get('total_time', 0):.1f}s\n"
        message += f"  • 平均耗时: {result.get('avg_time_per_image', 0):.1f}s/张\n"

        # 计算加速比（基于每张图像的实际处理时间）
        if result['success_count'] > 0 and result.get('images'):
            # 计算每张图像的平均实际处理时间
            total_single_time = sum(img.get('time', 0) for img in result.get('images', []))
            avg_single_time = total_single_time / result['success_count']

            # 串行总耗时 = 每张图像的平均实际处理时间 × 任务数
            serial_time = avg_single_time * result['total']

            # 加速比 = 串行总耗时 / 并发总耗时
            speedup = serial_time / result.get('total_time', 1) if result.get('total_time', 0) > 0 else 1.0

            message += f"  • 单张平均: {avg_single_time:.1f}s (实际处理时间)\n"
            message += f"  • 加速比: {speedup:.1f}x (相比串行)\n"

        message += f"  • 保存位置: {assets_dir}/\n"

        # 添加错误详情
        if result.get('errors'):
            message += f"\n❌ 错误详情：\n"
            for error in result['errors']:
                message += f"  • {error.get('name', '未知')}: {error.get('error', '未知错误')}\n"

        # 添加成功生成的图像列表
        if result['success_count'] > 0:
            message += f"\n✅ 已生成的素材：\n"
            for img_info in result.get('images', []):
                if img_info:
                    message += f"  • {img_info.get('filename', '未知')}"
                    message += f" [{img_info.get('target_size', 'N/A')}]"
                    message += f" [{img_info.get('style', 'N/A')}]"

                    # 显示处理时间
                    if img_info.get('time'):
                        message += f" ({img_info.get('time', 0):.1f}s)"

                    # 显示抠图信息
                    if img_info.get('background_removed') and img_info.get('pixels_removed', 0) > 0:
                        message += f" [已抠图: {img_info.get('pixels_removed', 0):,}像素]"

                    message += "\n"

        message += f"\n📝 任务文件已重置为空模板，可以继续添加新任务\n"

        return message

    except json.JSONDecodeError as e:
        return f"❌ 任务文件 JSON 格式错误:\n{str(e)}"
    except Exception as e:
        # 捕获详细的错误信息
        import traceback
        error_detail = traceback.format_exc()
        return f"❌ 生成过程中发生错误:\n\n{str(e)}\n\n详细错误:\n{error_detail}"


if __name__ == "__main__":
    mcp.run()
