# 快速上手指南

> 5 分钟快速上手游戏素材图像生成工具

## 🚀 快速开始

### 1️⃣ 安装依赖（首次使用）

```bash
# 进入工具目录
cd /home/leke/playground/sysp-img-test/img-gen-tool

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2️⃣ 配置 API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的豆包 API Key
nano .env
```

在 `.env` 文件中填入：
```
ARK_API_KEY=你的豆包API_Key
```

### 3️⃣ 配置 Qwen Code MCP

在 Qwen Code 的 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "image-gen-tool": {
      "command": "venvPATH/venv/bin/python",
      "args": [
        "toolsPATH/img-gen-tool/mcp_server.py"
      ],
      "timeout": 30000
    }
  },
  "$version": 2
}
```

**⚠️ 重要：** 如果你的工具目录不在这个位置，需要修改上面的路径！

### 4️⃣ 重启 Qwen Code

保存配置后，重启 Qwen Code 使 MCP 配置生效。

---

## 📝 第一次生成

### 步骤 1：在 Qwen Code 中调用

在 Qwen Code 中输入：

```
请帮我生成一个小猫图像
```

### 步骤 2：查看结果

生成的图像保存在：`your-project/public/assets/cute_cat.png`

## 📖 常用配置速查

### category（素材分类）

| 分类 | 用途 | 是否抠图 |
|------|------|---------|
| `char_portrait` | 角色立绘（对话框） | ✅ |
| `char_sprite` | 角色小人（游戏场景） | ✅ |
| `ui_asset` | UI 组件 | ✅ |
| `prop` | 道具物品 | ✅ |
| `background` | 背景图 | ❌ |
| `illustration` | 插画/CG | ❌ |

### style（美术风格）

- `pixel` - 像素风（8bit/16bit）
- `cartoon` - 卡通风（默认）
- `realistic` - 写实风

### size（图像尺寸）

`2048x2048` - 2K（默认）

---

## 🎯 批量生成示例

在 `tasks.json` 中添加多个任务：

```json
[
  {
    "description": "红色生命值图标",
    "category": "ui_asset",
    "style": "cartoon",
    "name": "hp_icon",
    "size": "1024x1024"
  },
  {
    "description": "蓝色魔法值图标",
    "category": "ui_asset",
    "style": "cartoon",
    "name": "mp_icon",
    "size": "1024x1024"
  },
  {
    "description": "金币道具",
    "category": "prop",
    "style": "cartoon",
    "name": "gold_coin",
    "size": "1024x1024"
  }
]
```

一次性生成所有素材！

---

## ⚠️ 常见错误

### 错误 1: "任务文件不存在"

**原因：** 没有在项目中创建 `public/tasks.json` 文件

**解决：** 在项目根目录创建 `public/tasks.json`

### 错误 2: "API Key 无效"

**原因：** `.env` 文件中的 API Key 错误或未配置

**解决：** 检查 `.env` 文件，确保 `ARK_API_KEY` 正确

### 错误 3: "MCP 工具找不到"

**原因：** MCP 配置路径错误或 Qwen Code 未重启

**解决：**
1. 检查 MCP 配置中的路径是否正确（必须使用绝对路径）
2. 重启 Qwen Code
3. 检查 `settings.json` 是否位于 `.qwen` 目录，命名是否正确

---

## 📚 下一步

- 阅读完整文档：[README.md](README.md)
- 了解所有参数：[参数详解](README.md#参数详解)
- 目录迁移：[迁移指南](README.md#目录迁移指南)

---

## 💡 小贴士

1. **description 不能为空**，否则任务会被跳过
2. **只有 background 和 illustration 不会抠图**，其他都会
3. 工具会自动生成 **name **
4. **生成完成后 tasks.json 会重置**，文件不会丢失，只是变成空模板
