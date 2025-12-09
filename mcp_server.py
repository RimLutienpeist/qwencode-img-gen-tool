# mcp_server.py
import sys
import os
import time
import json
from mcp.server.fastmcp import FastMCP

# 显式添加当前目录到 sys.path，确保能正确导入 main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 导入你现有的脚本 (main.py)
# 注意：导入时 main.py 顶部的 client 初始化代码会运行，请确保 .env 配置正确
try:
    import main as engine
except ImportError as e:
    print(f"错误：无法导入模块 - {e}")
    print("请确保 mcp_server.py 和 main.py 在同一目录下")
    sys.exit(1)

# 初始化 MCP 服务器
mcp = FastMCP("DoubaoAssetGenerator")

@mcp.tool()
def generate_game_asset(workspace_dir: str) -> str:
    """
    从 tasks.json 读取任务列表并批量生成游戏素材图像，自动移除白色背景。

    此工具会自动完成：
    1. 读取 workspace_dir/public/tasks.json 文件获取任务列表
    2. 为每个任务生成图像 (保存到 workspace_dir/public/assets/)
    3. 移除白色背景（除 background 和 illustration 外，其他分类会强制生成白色背景并自动抠图）
    4. 生成完成后清空 tasks.json 文件

    Args:
        workspace_dir: Qwen Code 的工作目录路径 (例如: "/home/user/phaser-frame-lite")

    tasks.json 格式:
    [
      {
        "description": "图像描述",
        "category": "char_portrait|char_sprite|ui_asset|sheet_effect|illustration|logo|prop|background|none",
        "style": "pixel|cartoon|realistic",
        "name": "文件名（不含后缀）",
        "size": "numxnum (例如 1024x512)"
      }
    ]
    """

    try:
        print(f"MCP 工具启动")
        print(f"工作目录: {workspace_dir}")

        # 1. 读取 tasks.json 文件
        tasks_json_path = os.path.join(workspace_dir, "public", "tasks.json")

        if not os.path.exists(tasks_json_path):
            return f"❌ 任务文件不存在: {tasks_json_path}"

        with open(tasks_json_path, "r", encoding="utf-8") as f:
            tasks_data = json.load(f)

        if not tasks_data or not isinstance(tasks_data, list):
            return f"❌ 任务文件格式错误，应该是一个数组"

        # 过滤掉空任务
        valid_tasks = [t for t in tasks_data if t.get("description") and t.get("description").strip()]

        if not valid_tasks:
            return f"ℹ️ 没有有效的任务需要执行（description 为空）"

        print(f"📋 读取到 {len(valid_tasks)} 个有效任务")

        # 2. 基于工作目录设置输出路径
        assets_dir = os.path.join(workspace_dir, "public", "assets")
        assets_dir = os.path.abspath(assets_dir)
        os.makedirs(assets_dir, exist_ok=True)

        # 3. 转换为 main.py 需要的格式
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

            print(f"  [{idx}] {name} - {category}/{style} - {description[:50]}...")

        # 4. 调用主程序生成图像
        result = engine.generate_images(engine_tasks, output_dir=assets_dir)

        # 5. 生成完成后，重置 tasks.json 文件为空模板
        try:
            # 保留一个空模板项，让用户知道要填入哪些信息
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
            print(f"✅ 已重置任务文件为空模板: {tasks_json_path}")
        except Exception as clear_error:
            print(f"⚠️ 重置任务文件失败: {clear_error}")

        # 6. 构建详细的返回消息
        message = f"{'='*60}\n"
        message += f"📊 批量生成完成！\n"
        message += f"{'='*60}\n\n"
        message += f"✅ 成功: {result['success_count']} 个\n"
        message += f"❌ 失败: {result['fail_count']} 个\n"
        message += f"📁 保存位置: {assets_dir}/\n"

        # 添加错误详情
        if result.get('errors'):
            message += f"\n{'='*60}\n"
            message += f"❌ 错误详情:\n"
            message += f"{'='*60}\n"
            for error in result['errors']:
                message += f"  • {error.get('name', '未知')}: {error.get('error', '未知错误')}\n"

        # 添加成功生成的图像列表
        if result['success_count'] > 0:
            message += f"\n{'='*60}\n"
            message += f"✅ 已生成的素材:\n"
            message += f"{'='*60}\n"
            for img_info in result.get('images', []):
                if img_info:
                    message += f"  • {img_info.get('filename', '未知')}"
                    message += f" [{img_info.get('size', 'N/A')}]"
                    message += f" [{img_info.get('style', 'N/A')}]"
                    if img_info.get('background_removed') and img_info.get('pixels_removed', 0) > 0:
                        message += f" (已抠图: {img_info.get('pixels_removed', 0):,} 像素)"
                    message += "\n"

        message += f"\n{'='*60}\n"
        message += f"💡 任务文件已重置为空模板，可以继续添加新任务\n"
        message += f"{'='*60}"

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
