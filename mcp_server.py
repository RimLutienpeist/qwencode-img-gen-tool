# mcp_server.py
import sys
import os
import time
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
def generate_game_asset(description: str, workspace_dir: str, category: str = "none", style: str = "cartoon", name: str = None) -> str:
    """
    根据描述生成游戏素材图像，自动移除绿幕背景。

    此工具会自动完成：
    1. 生成图像 (保存到 workspace_dir/public/assets/)
    2. 移除绿幕背景（除 background 和 illustration 外，其他分类会强制生成绿幕并自动抠图）

    Args:
        description: 图像的详细描述 (例如: "一个手持火焰剑的红发女战士")
        workspace_dir: Qwen Code 的工作目录路径 (例如: "/home/user/phaser-frame-lite")
        category: 素材分类，影响系统提示词。可选值:
            "char_portrait"(角色立绘), "char_sprite"(角色小人), "ui_asset"(UI组件),
            "sheet_effect"(序列帧特效), "illustration"(插画/CG), "logo"(标志/标题),
            "prop"(道具/物品), "background"(背景/底图), "none"(无)
        style: 美术风格。可选值: "pixel"(像素风), "cartoon"(卡通风), "realistic"(写实风)
        name: (可选) 保存的文件名，不含后缀。如果不填，会自动生成一个基于时间的名字。
    """
    
    # 1. 如果没提供名字，生成一个临时名字
    if not name:
        # 清理描述中的特殊字符作为文件名的一部分，或者直接用时间戳
        safe_desc = "".join([c for c in description if c.isalnum()])[:10]
        name = f"auto_{safe_desc}_{int(time.time())}"
    
    # 2. 判断是否需要绿幕（只有 background 和 illustration 不需要绿幕）
    no_green_screen_categories = ["background", "illustration"]
    is_background = category in no_green_screen_categories

    # 3. 构造任务对象 (完全复用 main.py 的逻辑)
    # main.py 的 generate_images 函数接受一个 task 列表
    # 我们这里构造一个只包含单条任务的列表
    task = {
        "name": name,
        "description": description,
        "category": category,
        "style": style,
        "need_green_screen": not is_background  # 背景图不需要绿幕，其他素材强制绿幕
    }

    # 3. 调用主程序逻辑
    try:
        print(f"MCP 接收到任务: {name} - {description}")
        print(f"工作目录: {workspace_dir}")

        # 基于工作目录设置输出路径
        assets_dir = os.path.join(workspace_dir, "public", "assets")
        assets_dir = os.path.abspath(assets_dir)

        # 确保目录存在
        os.makedirs(assets_dir, exist_ok=True)

        # 调用主程序生成图像
        result = engine.generate_images([task], output_dir=assets_dir)

        # 生成完成后，清空 workspace_dir/public/tasks.json 文件
        try:
            task_json_path = os.path.join(workspace_dir, "public", "tasks.json")
            # 如果文件存在，清空内容；如果不存在，创建空文件
            with open(task_json_path, "w", encoding="utf-8") as f:
                f.write("")
            print(f"✅ 已清空任务文件: {task_json_path}")
        except Exception as clear_error:
            print(f"⚠️ 清空任务文件失败: {clear_error}")
            # 不影响主流程，继续执行

        # 构建详细的返回消息
        if result["success"]:
            # 获取生成的图像信息
            img_info = result["images"][0] if result["images"] else {}

            message = f"✅ 图像生成成功！\n\n"
            message += f"文件名: {name}.png\n"
            message += f"风格: {style}\n"
            message += f"分类: {category}\n"
            message += f"保存位置: {os.path.join(workspace_dir, 'public', 'assets', f'{name}.png')}\n"

            # 添加绿幕移除信息
            if img_info.get('green_screen_removed'):
                pixels = img_info.get('pixels_removed', 0)
                message += f"\n🎨 绿幕已移除 (处理了 {pixels:,} 个像素)"

            # 添加使用的完整提示词
            if img_info.get('prompt'):
                prompt = img_info['prompt']
                # 截断过长的提示词
                if len(prompt) > 150:
                    prompt_display = prompt[:150] + "..."
                else:
                    prompt_display = prompt
                message += f"\n\n📝 使用的提示词:\n{prompt_display}"

            return message
        else:
            # 生成失败时，返回详细的错误信息
            message = f"❌ 生成失败\n\n"
            message += f"成功: {result['success_count']}\n"
            message += f"失败: {result['fail_count']}\n"

            # 添加错误详情
            if result.get('errors'):
                message += f"\n错误详情:\n"
                for error in result['errors']:
                    message += f"- {error.get('name', '未知')}: {error.get('error', '未知错误')}\n"

            return message

    except Exception as e:
        # 捕获详细的错误信息
        import traceback
        error_detail = traceback.format_exc()
        return f"❌ 生成过程中发生错误:\n\n{str(e)}\n\n详细错误:\n{error_detail}"



if __name__ == "__main__":
    mcp.run()