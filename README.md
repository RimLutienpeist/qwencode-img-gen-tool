# 游戏素材图像生成工具 - 使用说明

## 📋 目录

- [工具简介](#工具简介)
- [环境要求](#环境要求)
- [安装配置](#安装配置)
- [使用方法](#使用方法)
- [tasks.json 格式说明](#tasksjson-格式说明)
- [参数详解](#参数详解)
- [常见问题](#常见问题)
- [目录迁移指南](#目录迁移指南)
- [故障排除](#故障排除)

---

## 工具简介

这是一个基于豆包（Doubao）API 的游戏素材图像生成 MCP 工具，可以：

- **批量生成游戏素材图像**：从 `tasks.json` 读取任务列表并批量生成
- **自动绿幕抠图**：自动为角色、道具等素材生成绿幕背景并抠图
- **智能分类处理**：根据素材类型（角色、UI、背景等）添加合适的系统提示词
- **与 Qwen Code 集成**：作为 MCP 工具，可在 Qwen Code 中直接调用

---

## 环境要求

### Python 环境
- Python 3.8+
- 虚拟环境（推荐）

### 依赖库
- `openai` - 豆包 API 客户端
- `python-dotenv` - 环境变量管理
- `pillow` - 图像处理
- `numpy` - 数值计算
- `requests` - HTTP 请求
- `mcp` - MCP 服务器框架

### API 要求
- 豆包 API Key（图像生成）

---

## 安装配置

### 1. 创建虚拟环境

```bash
cd /home/leke/playground/sysp-img-test/img-gen-tool
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 2. 安装依赖

```bash
pip install openai python-dotenv pillow numpy requests mcp
```

### 3. 配置 API Key

在工具目录下创建 `.env` 文件：

```bash
# .env 文件内容
ARK_API_KEY=your_doubao_api_key_here
```

**获取 API Key：**
1. 访问豆包开放平台
2. 创建应用并获取 API Key
3. 复制到 `.env` 文件中

### 4. 配置 MCP 服务器

在 Qwen Code 的 MCP 配置中添加：

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

**⚠️ 重要：** 测试时使用的是绝对路径，不知道能不能用相对路径。

---

## 使用方法

### 工作流程

```
1. Qwen Code 编辑 tasks.json
   ↓
2. 调用 MCP 工具 generate_game_asset(workspace_dir)
   ↓
3. 工具读取 tasks.json 并批量生成图像
   ↓
4. 图像保存到 workspace_dir/public/assets/
   ↓
5. tasks.json 重置为空模板
```

### 步骤 1：Qwen Code 准备 tasks.json

例如，在 Qwen Code 中执行：

```
请生成一张女战士立绘和一张森林背景图
```

> [!IMPORTANT]
>
> size 参数不同模型支持的写法不同，例如 seedream4.0 支持写 `2K`，而 seedream3.0 不支持，只能写 `1920x1080` 这种

qwen code 会在项目的 `public/tasks.json` 文件中填写任务，例如：

```json
[
  {
    "description": "一个手持火焰剑的红发女战士", 	# 会用做prompt的主体部分
    "category": "char_portrait",				# 不同类别会附加不同的类别提示词
    "style": "cartoon",							# 不同风格会附加不同的风格提示词
    "name": "warrior_portrait",					# 图像命名
    "size": "2048x2048"							# 图像长宽
  },
  {
    "description": "森林场景背景",
    "category": "background",
    "style": "realistic",
    "name": "forest_bg",
    "size": "1024x1024"
  }
]
```

### 步骤 2： Qwen Code 调用工具

### 步骤 3：查看生成结果

- **图像位置**：`$workspace_dir$/public/assets/`
- **文件名**：`{name}.png`
- **tasks.json**：已重置为空模板

---

## tasks.json 格式说明

### 完整示例

```json
[
  {
    "description": "图像描述",
    "category": "素材分类",
    "style": "美术风格",
    "name": "文件名",
    "size": "图像尺寸"
  }
]
```

### 字段说明

| 字段 | 是否必填 | 默认值 | 说明 |
|------|---------|--------|------|
| `description` | ✅ 必填 | 无 | 图像的详细描述，如 "一个手持火焰剑的红发女战士" |
| `category` | ❌ 可选 | `"none"` | 素材分类，影响系统提示词和是否抠图 |
| `style` | ❌ 可选 | `"cartoon"` | 美术风格 |
| `name` | ❌ 可选 | 自动生成 | 保存的文件名（不含 .png 后缀） |
| `size` | ❌ 可选 | `"2048x2048"` | 图像尺寸 |

### 注意事项

1. **description 为空的任务会被跳过**
2. 可以在数组中添加多个任务对象，工具会批量处理
3. 生成完成后 `tasks.json` 会重置为空模板

---

## 参数详解

### category（素材分类）

| 值 | 说明 | 绿幕抠图 | 系统提示词 |
|----|------|---------|-----------|
| `char_portrait` | 角色立绘 | ✅ 是 | 角色立绘，清晰轮廓，立绘设计，适合对话界面使用 |
| `char_sprite` | 角色小人 | ✅ 是 | 角色小人，游戏精灵，清晰轮廓，适合游戏场景使用 |
| `ui_asset` | UI 组件 | ✅ 是 | UI 组件，界面元素，清晰可辨识，扁平化设计 |
| `sheet_effect` | 序列帧特效 | ✅ 是 | 序列帧特效，动态效果，连续帧设计，发光效果 |
| `logo` | 标志/标题 | ✅ 是 | 标志设计，标题文字，清晰可辨识，品牌感 |
| `prop` | 道具/物品 | ✅ 是 | 道具物品，物品设计，清晰轮廓，适合游戏使用 |
| `illustration` | 插画/CG | ❌ 否 | 插画设计，CG 场景，完整构图，丰富细节 |
| `background` | 背景/底图 | ❌ 否 | 背景设计，场景底图，适合横向/纵向卷轴，层次分明 |
| `none` | 无分类 | ✅ 是 | 仅添加基础提示词 |

**重要说明：**
- 只有 `background` 和 `illustration` **不会** 生成绿幕和抠图
- 其他所有分类都会 **强制** 生成绿幕背景并自动抠图

### style（美术风格）

| 值 | 说明 | 系统提示词 |
|----|------|-----------|
| `pixel` | 像素风 | 像素风格，8bit/16bit 复古游戏风格，清晰的像素边界 |
| `cartoon` | 卡通风 | 漫画风格，卡通渲染，cel-shading，明快色彩 |
| `realistic` | 写实风 | 写实风格，3D 渲染，高细节，真实质感 |

### size（图像尺寸）

默认：`"2048x2048"` - 2K 分辨率（）

## 常见问题

### Q1: 图像生成失败怎么办？

**检查清单：**
1. ✅ `.env` 文件中的 API Key 是否正确
2. ✅ 网络连接是否正常
3. ✅ `tasks.json` 格式是否正确
4. ✅ `description` 字段是否为空

**查看错误信息：**
工具会在返回消息中显示详细的错误信息。

### Q2: 如何修改默认风格？

在 `main.py` 中修改：

```python
# 默认美术风格
ART_STYLE = "cartoon"  # 改为 "pixel" 或 "realistic"
```

### Q3: 如何调整绿幕抠图的灵敏度？

在 `main.py` 中修改：

```python
GREEN_SCREEN_CONFIG = {
    "skip_backgrounds": True,
    "overwrite": True,
    "tolerance": 40,    # 增大此值可移除更多绿色区域（0-100）
    "threshold": 100,   # 绿色阈值（0-255）
}
```

### Q4: tasks.json 被清空了怎么恢复？

工具不会完全清空，会保留一个空模板：

```json
[
  {
    "description": "",
    "category": "",
    "style": "",
    "name": "",
    "size": ""
  }
]
```

直接在模板基础上填写新任务即可。

### Q5: 可以同时生成多少个任务？

理论上没有限制，但建议：
- 单次生成不超过 10 个任务
- 大批量任务可分多次执行

---

## 目录迁移指南

如果需要将工具迁移到其他目录，需要修改以下配置：

### 1. 修改 Qwen Code 的 MCP 配置

假设新目录为 `/new/path/to/img-gen-tool`：

```json
{
  "mcpServers": {
    "image-gen-tool": {
      "command": "venvPATH/venv/bin/python",
      "args": [
        "/new/path/to/img-gen-tool/mcp_server.py"
      ],
      "timeout": 30000
    }
  },
  "$version": 2
}
```

**⚠️ 必须修改的路径：**
- `command`: 虚拟环境中的 Python 解释器路径
- `args[1]`: mcp_server.py 的路径（最好是绝对路径，相对路径没试过）

### 2. 检查 .env 文件

确保新目录下有 `.env` 文件（包含 api key）：

```bash
cp /old/path/.env /new/path/to/img-gen-tool/.env
```

### 3. 重新创建虚拟环境（推荐）

假如虚拟环境在工具目录下：

```bash
cd /new/path/to/img-gen-tool
python3 -m venv venv
source venv/bin/activate
pip install openai python-dotenv pillow numpy requests mcp
```

### 4. 重启 Qwen Code MCP 服务器

修改配置后，需要重启 Qwen Code 或重新加载 MCP 配置。

### 迁移检查清单

- [ ] 复制所有文件到新目录
- [ ] 复制或创建 `.env` 文件
- [ ] 创建新的虚拟环境并安装依赖
- [ ] 更新 Qwen Code MCP 配置中的路径
- [ ] 重启 Qwen Code
- [ ] 测试工具是否正常工作

---

## 故障排除

### 问题 1: MCP 工具无法找到

**症状：** Qwen Code 中找不到 `generate_game_asset` 工具

**解决方案：**
1. 检查 MCP 配置文件路径是否正确
2. 确认使用绝对路径
3. 重启 Qwen Code
4. 查看 Qwen Code 的 MCP 日志

### 问题 2: 模块导入失败

**症状：** 错误信息显示 "无法导入模块"

**解决方案：**
1. 确认虚拟环境已激活
2. 重新安装依赖：`pip install -r requirements.txt`
3. 检查 Python 版本是否符合要求

### 问题 3: API Key 无效

**症状：** 错误信息显示 "Authentication failed" 或 "Invalid API key"

**解决方案：**
1. 检查 `.env` 文件是否存在
2. 确认 `ARK_API_KEY` 是否正确
3. 检查 API Key 是否过期
4. 确认 API Key 有图像生成权限

### 问题 4: 绿幕抠图不完整

**症状：** 图像边缘仍有绿色残留

**解决方案：**
1. 增加 `tolerance` 值（在 `main.py` 的 `GREEN_SCREEN_CONFIG` 中）
2. 调整 `threshold` 值
3. 尝试重新生成图像

### 问题 5: tasks.json 格式错误

**症状：** 错误信息显示 "JSON 格式错误"

**解决方案：**
1. 使用 JSON 验证工具检查格式
2. 确保所有字符串都用双引号
3. 确保最后一项没有多余的逗号
4. 确保外层是数组 `[]`

---

## 附录

### 完整示例：tasks.json

```json
[
  {
    "description": "一个手持火焰剑的红发女战士，全身立绘",
    "category": "char_portrait",
    "style": "cartoon",
    "name": "warrior_portrait",
    "size": "2048x2048"
  },
  {
    "description": "Q版矮人角色，适合游戏场景使用",
    "category": "char_sprite",
    "style": "pixel",
    "name": "dwarf_sprite",
    "size": "1024x1024"
  },
  {
    "description": "生命值显示的红色心形图标",
    "category": "ui_asset",
    "style": "cartoon",
    "name": "health_icon",
    "size": "1024x1024"
  },
  {
    "description": "火焰爆炸特效，8帧序列",
    "category": "sheet_effect",
    "style": "cartoon",
    "name": "fire_explosion",
    "size": "2048x2048"
  },
  {
    "description": "金币道具，闪闪发光",
    "category": "prop",
    "style": "cartoon",
    "name": "gold_coin",
    "size": "1024x1024"
  },
  {
    "description": "中世纪城堡大厅的背景图",
    "category": "background",
    "style": "realistic",
    "name": "castle_hall_bg",
    "size": "2048x2048"
  },
  {
    "description": "游戏标题：勇者传说",
    "category": "logo",
    "style": "cartoon",
    "name": "game_title",
    "size": "2048x2048"
  },
  {
    "description": "精美的游戏CG插画，史诗战斗场景",
    "category": "illustration",
    "style": "realistic",
    "name": "epic_battle_cg",
    "size": "2048x2048"
  }
]
```

### 文件结构

```
img-gen-tool/
├── main.py                 # 核心图像生成逻辑
├── mcp_server.py          # MCP 服务器入口
├── .env                   # API Key 配置（不要提交到 Git）
├── README.md              # 本文档
├── venv/                  # Python 虚拟环境（不要提交到 Git）
└── requirements.txt       # 依赖列表（可选）
```

### requirements.txt（可选创建）

```txt
openai>=1.0.0
python-dotenv>=1.0.0
pillow>=10.0.0
numpy>=1.24.0
requests>=2.31.0
mcp>=0.1.0
```

安装依赖：`pip install -r requirements.txt`

---

**最后更新时间：** 2025-12-04
**文档版本：** v1.0
