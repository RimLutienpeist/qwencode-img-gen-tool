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

    ⚠️ IMPORTANT LIMITATION: This tool generates ONLY single static images. It CANNOT generate sprite sheets, animation frames, or frame sequences.

    Core Functions:
    1. Read the task list from the workspace_dir/public/tasks.json file.
    2. Concurrently generate multiple images (Save to workspace_dir/public/assets/).
    3. Automatically identify and remove the background, exporting transparent PNGs (Background removal is conditional on the category).
    4. Reset tasks.json to an empty template after generation is complete.

    Background Processing Rules:
    - 'background' and 'illustration' categories: Keep the original background (No removal).
    - Other categories (Character, UI, Prop, etc.): Automatically detect and remove the background color.

    Intelligent Size Optimization:
    - Supports arbitrary sizes (e.g., 128x128, 1024x1024, 4096x4096).

    ⚠️ Animation Limitation:
    - Each task generates ONE single static image only
    - Cannot generate walking cycles, attack sequences, or any multi-frame animations
    - For character movement, design single-pose sprites and use Phaser's programmatic animations (rotation, scale, position)

    Args:
        workspace_dir: Path to the working directory of Qwen Code (e.g., "/home/user/phaser-frame-lite").

    tasks.json Format:
    [
        {
        "description": "Image description (Required)",
        "category": "char_portrait|char_sprite|ui_asset|effect|illustration|logo|prop|background",
        "style": "pixel|cartoon|realistic",
        "viewpoint": "e.g. front|back|side|top|isometric|perspective",
        "name": "Filename (without extension)",
        "size": "Width x Height (e.g., 1024x512)"
        }
    ]

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
    - front: Front view (正面视角)
    - back: Back view (背面视角)
    - side: Side view (侧面视角)
    - top: Top-down view (俯视视角)
    - isometric: Isometric view (等轴测视角)
    - perspective: Perspective view (透视视角)
    - three_quarter: Three-quarter view (四分之三视角)

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

        # 3. 转换为 main_async.py 需要的格式
        engine_tasks = []
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

            engine_tasks.append({
                "name": name,
                "description": description,
                "category": category,
                "style": style,
                "viewpoint": viewpoint,  # 添加视角参数
                "size": size,
                "need_white_background": not is_background
            })

            # 日志中包含视角信息
            viewpoint_info = f" (视角: {viewpoint})" if viewpoint else ""
            logger.info(f"  [{idx}] {name} - {category}/{style}{viewpoint_info} - {description[:50]}...")

        # 4. 调用主程序生成图像（并发版本）
        result = engine.generate_images_concurrent(
            engine_tasks,
            output_dir=assets_dir,
            max_concurrent=max_concurrent
        )

        # 5. 生成完成后，重置 tasks.json 文件为空模板
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
            with open(tasks_json_path, "w", encoding="utf-8") as f:
                json.dump(template, f, ensure_ascii=False, indent=2)
            logger.info(f"已重置任务文件为空模板: {tasks_json_path}")
        except Exception as clear_error:
            logger.error(f"重置任务文件失败: {clear_error}")

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
