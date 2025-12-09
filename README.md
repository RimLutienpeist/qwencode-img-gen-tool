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
- **智能白色背景抠图**：使用 GrabCut 图割算法自动移除白色背景，边缘平滑，支持半透明效果
- **自动颜色校正**：智能增强边缘饱和度，去除灰白色溢出，提升抠图质量
- **智能尺寸优化**：自动选择最佳 API 尺寸（512-2048），支持任意目标尺寸
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
- `opencv-python` - 图像处理（GrabCut 抠图算法）

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
pip install openai python-dotenv pillow numpy requests mcp opencv-python
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
      "timeout": 300000
    }
  },
  "$version": 2
}
```

**⚠️ 重要提示：**
- **超时时间**：建议设置为 `300000`（5 分钟）或更高
  - 单张图像生成通常需要 10-30 秒
  - 批量生成多张图会更久
  - GrabCut 算法比简单算法慢约 2-3 倍
- **路径配置**：测试时使用的是绝对路径，相对路径可能不可靠

---

## 使用方法

### 工作流程

```
1. Qwen Code 编辑 tasks.json
   ↓
2. 调用 MCP 工具 generate_game_asset(workspace_dir)
   ↓
3. 工具读取 tasks.json 并批量生成图像
   ├─ 智能计算最佳 API 尺寸（512-2048 范围）
   ├─ 调用 API 生成图像
   ├─ 自动移除白色背景（如需要）
   └─ 自动缩放到目标尺寸（如需要）
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
> **智能尺寸处理机制：**
>
> - **512x512 - 2048x2048 范围内**：直接传给 API 生成，无需后处理（最佳质量）
> - **小于 512x512**：自动放大到范围内生成，然后缩小回目标尺寸
>   - 例如：256x256 → 512x512 生成 → 缩小为 256x256
> - **大于 2048x2048**：自动缩小到范围内生成，然后放大到目标尺寸
>   - 例如：4096x4096 → 2048x2048 生成 → 放大为 4096x4096
> - 支持任意尺寸，格式为 `宽x高`（例如：`2048x2048`、`512x512`、`128x128`、`4096x4096`）
> - 使用高质量 LANCZOS 算法缩放

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

```python
            # 调用豆包图像生成 API（固定使用 1024x1024）
            # imagesResponse = client.images.generate(
            #     # model="doubao-seedream-4-0-250828",
            #     model="doubao-seedream-3-0-t2i-250415",
            #     prompt=prompt,
            #     size=api_size,  # 固定使用 1024x1024
            #     response_format="url",
            #     extra_body={
            #         "watermark": False,  # 设置为 False 移除水印
            #     },
            # )
```

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

| 字段            | 是否必填 | 默认值          | 说明                                            |
| --------------- | -------- | --------------- | ----------------------------------------------- |
| `description` | ✅ 必填  | 无              | 图像的详细描述，如 "一个手持火焰剑的红发女战士" |
| `category`    | ❌ 可选  | `"none"`      | 素材分类，影响系统提示词和背景颜色              |
| `style`       | ❌ 可选  | `"cartoon"`   | 美术风格                                        |
| `name`        | ❌ 可选  | 自动生成        | 保存的文件名（不含 .png 后缀）                  |
| `size`        | ❌ 可选  | `"2048x2048"` | 图像尺寸                                        |

### 注意事项

1. **description 为空的任务会被跳过**
2. 可以在数组中添加多个任务对象，工具会批量处理
3. 生成完成后 `tasks.json` 会重置为空模板

---

## 参数详解

### category（素材分类）

| 值                | 说明       | 白色背景 | 系统提示词                                      |
| ----------------- | ---------- | -------- | ----------------------------------------------- |
| `char_portrait` | 角色立绘   | ✅ 是    | 角色立绘，清晰轮廓，立绘设计，适合对话界面使用  |
| `char_sprite`   | 角色小人   | ✅ 是    | 角色小人，游戏精灵，清晰轮廓，适合游戏场景使用  |
| `ui_asset`      | UI 组件    | ✅ 是    | UI 组件，界面元素，清晰可辨识，扁平化设计       |
| `sheet_effect`  | 序列帧特效 | ✅ 是    | 序列帧特效，动态效果，连续帧设计，发光效果      |
| `logo`          | 标志/标题  | ✅ 是    | 标志设计，标题文字，清晰可辨识，品牌感，必须使用纯白色背景 |
| `prop`          | 道具/物品  | ✅ 是    | 道具物品，物品设计，清晰轮廓，适合游戏使用      |
| `illustration`  | 插画/CG    | ❌ 否    | 插画设计，CG 场景，完整构图，丰富细节           |
| `background`    | 背景/底图  | ❌ 否    | 背景设计，场景底图，适合横向/纵向卷轴，层次分明 |
| `none`          | 无分类     | ✅ 是    | 仅添加基础提示词                                |

**重要说明：**

- 只有 `background` 和 `illustration` **不会** 生成白色背景
- 其他所有分类都会 **强制** 生成纯白色背景并自动抠图

### style（美术风格）

| 值            | 说明   | 系统提示词                                        |
| ------------- | ------ | ------------------------------------------------- |
| `pixel`     | 像素风 | 像素风格，8bit/16bit 复古游戏风格，清晰的像素边界 |
| `cartoon`   | 卡通风 | 漫画风格，卡通渲染，cel-shading，明快色彩         |
| `realistic` | 写实风 | 写实风格，3D 渲染，高细节，真实质感               |

### size（图像尺寸）

**智能尺寸处理机制：**

工具会根据目标尺寸自动选择最佳生成策略：

1. **512x512 - 2048x2048 范围内**
   - API 直接使用目标尺寸生成
   - 无需后处理，**最佳质量**
   - 例如：`1024x1024`、`1920x1080`、`2048x2048`

2. **小于 512x512**
   - 自动放大到 512 范围内（2 的幂次倍数）
   - 生成后缩小回目标尺寸
   - 例如：`256x256` → 生成 `512x512` → 缩小为 `256x256`
   - 例如：`128x128` → 生成 `512x512` → 缩小为 `128x128`

3. **大于 2048x2048**
   - 自动缩小到 2048 范围内（2 的幂次倍数）
   - 生成后放大到目标尺寸
   - 例如：`4096x4096` → 生成 `2048x2048` → 放大为 `4096x4096`

**支持的尺寸格式：**

- 格式：`"宽x高"`（注意是小写 x）
- 默认：`"1024x1024"`
- 支持任意尺寸，工具会自动优化

**常用尺寸示例：**

| 尺寸 | 类型 | API 策略 | 后处理 |
|------|------|---------|--------|
| `128x128` | 小图标 | 生成 512x512 | 缩小 4 倍 |
| `256x256` | UI 图标 | 生成 512x512 | 缩小 2 倍 |
| `512x512` | 标准图标 | 生成 512x512 | ✅ 无需处理 |
| `1024x1024` | 标准素材 | 生成 1024x1024 | ✅ 无需处理 |
| `1920x1080` | 横向背景 | 生成 1920x1080 | ✅ 无需处理 |
| `2048x2048` | 高清素材 | 生成 2048x2048 | ✅ 无需处理 |
| `4096x4096` | 超高清 | 生成 2048x2048 | 放大 2 倍 |

**缩放质量保证：**

- 使用高质量 LANCZOS 重采样算法
- 放大：保持较好的清晰度
- 缩小：抗锯齿效果好，无锯齿感

## 常见问题

### Q1: MCP error -32001: Request timed out 怎么办？

**症状：** 图像生成成功了，但 Qwen Code 报告超时错误

**原因：** MCP 服务器等待响应超时（默认 30 秒不够）

**解决方案：**

1. **增加 MCP 配置中的 timeout 值**（推荐）：
   ```json
   {
     "mcpServers": {
       "image-gen-tool": {
         "timeout": 300000  // 改为 300000 (5分钟) 或更高
       }
     }
   }
   ```

2. **优化处理速度**（如果仍然超时）：
   - 减少批量生成的图像数量（建议单次不超过 5 张）
   - 使用 `simple` 算法代替 `grabcut`（速度快 2-3 倍）
   - 减少 `grabcut_iterations` 值（从 5 降到 3）

3. **重启 Qwen Code** 使配置生效

### Q2: 图像生成失败怎么办？

**检查清单：**

1. ✅ `.env` 文件中的 API Key 是否正确
2. ✅ 网络连接是否正常
3. ✅ `tasks.json` 格式是否正确
4. ✅ `description` 字段是否为空

**查看错误信息：**
工具会在返回消息中显示详细的错误信息。

### Q3: 如何修改默认风格？

在 `main.py` 中修改：

```python
# 默认美术风格
ART_STYLE = "cartoon"  # 改为 "pixel" 或 "realistic"
```

### Q4: 如何调整背景移除的灵敏度和算法？

在 `main.py` 中修改：

```python
BACKGROUND_REMOVAL_CONFIG = {
    "skip_backgrounds": True,
    "overwrite": True,
    "tolerance": 40,              # 颜色容差（0-100，数值越大移除范围越广）
    "threshold": 200,             # 白色阈值（0-255，建议 200-240）
    "algorithm": "grabcut",       # 算法选择: "simple" 或 "grabcut"
    "grabcut_iterations": 5,      # GrabCut 迭代次数（1-10，越大越精确但越慢）
    "edge_feather": 3,            # 边缘羽化半径（像素，0 表示不羽化）
    "remove_color_spill": True,   # 是否移除颜色溢出（边缘色彩校正）
}
```

**算法说明：**

- **`"grabcut"`**（推荐，默认）：
  - 使用 OpenCV GrabCut 图割算法
  - 边缘平滑，支持半透明效果
  - 自动增强边缘饱和度，去除灰白色溢出
  - 适合需要高质量抠图的场景（角色、道具等）

- **`"simple"`**（快速，但边缘生硬）：
  - 使用简单的颜色阈值检测
  - 速度快，但边缘有锯齿
  - 适合对边缘质量要求不高的场景

**参数调优建议：**

- `threshold`：白色阈值，200-240 之间通常效果最好，过低会误移除浅色物体
- `tolerance`：颜色容差，默认 40，如果有彩色背景残留可减小此值
- `grabcut_iterations`：默认 5 次通常足够，复杂图像可增加到 8-10
- `edge_feather`：默认 3 像素，增大可获得更柔和的边缘

### Q5: tasks.json 被清空了怎么恢复？

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

### Q6: 可以同时生成多少个任务？

理论上没有限制，但建议：

- **单次生成不超过 5-10 个任务**
- 大批量任务可分多次执行
- 注意 MCP 超时限制（见 Q1）
  - 使用 GrabCut 算法时，建议单次不超过 5 张
  - 使用 Simple 算法时，可以增加到 10 张

### Q7: 智能尺寸处理是如何工作的？

**工作原理：**

工具会根据目标尺寸自动选择最佳策略，兼顾质量和灵活性：

1. **优先使用原生尺寸**（512-2048 范围）
   - 直接传给 API，生成质量最好
   - 无需后处理，速度最快

2. **自动优化超范围尺寸**
   - 小尺寸（<512）：先放大生成，再缩小
   - 大尺寸（>2048）：先缩小生成，再放大
   - 使用 2 的幂次倍数，保证缩放质量

**为什么这样设计？**

1. **API 限制**：豆包模型仅支持 512x512 - 2048x2048 范围
2. **质量优先**：范围内直接生成，无损质量
3. **灵活性**：支持任意尺寸，自动优化
4. **高质量缩放**：LANCZOS 算法，效果接近原生生成

**最佳实践：**

- 推荐使用 512-2048 范围内的尺寸（无需后处理）
- 如需 4K（4096x4096），会从 2048x2048 放大
- 如需小图标（128x128），会从 512x512 缩小
- 提示词中加入"高清、细节丰富"可提升生成质量

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

### 问题 4: 背景移除不完整

**症状：** 图像边缘仍有白色/灰色残留

**解决方案：**

1. 调整 `threshold` 值（在 `main.py` 的 `BACKGROUND_REMOVAL_CONFIG` 中）- 降低阈值可移除更多浅色区域
2. 调整 `tolerance` 值 - 减小此值可以更严格地判断白色
3. 增加 `grabcut_iterations` 值 - 提高迭代次数可以改善边缘质量
4. 尝试重新生成图像

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
    "size": "512x512"
  },
  {
    "description": "生命值显示的红色心形图标",
    "category": "ui_asset",
    "style": "cartoon",
    "name": "health_icon",
    "size": "256x256"
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
    "size": "1920x1080"
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
opencv-python>=4.0.0
```

安装依赖：`pip install -r requirements.txt`

---

**最后更新时间：** 2025-12-09
**文档版本：** v1.2 - 白色背景替代绿幕，优化抠图效果
