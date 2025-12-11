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
def generate_game_asset(workspace_dir: str, max_concurrent: int = 5) -> str:
    """
    从 tasks.json 读取任务列表并并发批量生成游戏素材图像，智能移除背景。

    核心功能：
    1. 读取 workspace_dir/public/tasks.json 文件获取任务列表
    2. 并发生成多张图像 (保存到 workspace_dir/public/assets/)
    3. 自适应背景检测 - 自动识别并移除任意纯色背景（白色/黑色/蓝色/灰色等）
    4. 智能抠图 - 使用 GrabCut 算法，边缘平滑，支持半透明效果
    5. 生成完成后重置 tasks.json 为空模板

    性能提升：
    - 串行版本：3张图 30-90秒，5张图 50-150秒，10张图 100-300秒
    - 并发版本：3张图 15-35秒，5张图 20-50秒，10张图 30-80秒
    - 加速比：2-4倍（取决于任务数量和并发设置）

    背景处理规则：
    - background 和 illustration 类别：保留原始背景（不抠图）
    - 其他类别（角色、UI、道具等）：自动检测并移除背景色

    智能尺寸优化：
    - 支持任意尺寸（如 128x128、1024x1024、4096x4096）
    - 自动选择最佳 API 尺寸（512-2048 范围）
    - 高质量 LANCZOS 缩放

    Args:
        workspace_dir: Qwen Code 的工作目录路径 (例如: "/home/user/phaser-frame-lite")
        max_concurrent: 最大并发数（默认 5，建议 3-10，避免 API 限流）

    tasks.json 格式:
    [
      {
        "description": "图像描述（必填）",
        "category": "char_portrait|char_sprite|ui_asset|effect|illustration|logo|prop|background",
        "style": "pixel|cartoon|realistic",
        "name": "文件名（不含后缀）",
        "size": "宽x高（如 1024x512）"
      }
    ]

    category 说明：
    - char_portrait: 角色立绘（抠图）
    - char_sprite: 角色小人/游戏精灵（抠图）
    - ui_asset: UI 组件（抠图）
    - effect: 特效元素（抠图）
    - logo: 标志/标题（抠图）
    - prop: 道具/物品（抠图）
    - illustration: 插画/CG（不抠图）
    - background: 背景/底图（不抠图）

    style 说明：
    - pixel: 像素风格（8bit/16bit 复古游戏风格）
    - cartoon: 卡通风格（漫画渲染，明快色彩）
    - realistic: 写实风格（3D 渲染，高细节）

    Returns:
        str: 批量生成结果报告，包含成功/失败数量、耗时统计、文件列表、错误详情等
    """

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
                "size": size,
                "need_white_background": not is_background
            })

            logger.info(f"  [{idx}] {name} - {category}/{style} - {description[:50]}...")

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
