# API 配置指南

本工具支持两种图像生成 API：

## 1. OpenAI DALL-E API（默认）

### 配置步骤

#### 1.1 获取 API Key
1. 访问 https://platform.openai.com/api-keys
2. 创建新的 API Key
3. 复制 Key

#### 1.2 配置 .env 文件
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

#### 1.3 代码配置（已默认启用）
`main.py` 中的配置：
```python
# 使用 OpenAI API (DALL-E)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)
```

#### 1.4 API 参数
```python
imagesResponse = client.images.generate(
    model="dall-e-3",          # 模型：dall-e-3 或 dall-e-2
    prompt=prompt,             # 提示词
    n=1,                       # 生成数量（DALL-E 3 仅支持 1）
    size="1024x1024",          # 尺寸：1024x1024, 1024x1792, 1792x1024
    quality="standard",        # 质量：standard 或 hd（仅 DALL-E 3）
    # style="natural",         # 风格：natural 或 vivid（仅 DALL-E 3）
    response_format="url"      # 返回格式：url 或 b64_json
)
```

### 支持的尺寸
- **DALL-E 3**: `1024x1024`, `1024x1792`, `1792x1024`
- **DALL-E 2**: `256x256`, `512x512`, `1024x1024`

### 费用参考（DALL-E 3）
- **Standard** (1024×1024): $0.040 / 张
- **Standard** (1024×1792, 1792×1024): $0.080 / 张
- **HD** (1024×1024): $0.080 / 张
- **HD** (1024×1792, 1792×1024): $0.120 / 张

---

## 2. 豆包 API（备用）

### 配置步骤

#### 2.1 获取 API Key
1. 访问豆包开放平台
2. 创建应用并获取 API Key

#### 2.2 配置 .env 文件
```bash
ARK_API_KEY=your_doubao_api_key_here
```

#### 2.3 修改代码配置
在 `main.py` 中，注释掉 OpenAI 配置，启用豆包配置：

```python
# 注释掉 OpenAI 配置
# client = OpenAI(
#     api_key=os.environ.get("OPENAI_API_KEY"),
# )

# 启用豆包配置
client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=os.environ.get("ARK_API_KEY"),
)
```

#### 2.4 修改 API 调用
在 `main.py` 的 `generate_images` 函数中，修改 API 调用：

```python
# 注释掉 DALL-E 调用
# imagesResponse = client.images.generate(
#     model="dall-e-3",
#     ...
# )

# 启用豆包调用
imagesResponse = client.images.generate(
    model="doubao-seedream-3-0-t2i-250415",  # 或其他豆包模型
    prompt=prompt,
    size=api_size,
    response_format="url",
    extra_body={
        "watermark": False,
    },
)
```

---

## 3. 快速切换 API

### 方法 1：使用环境变量判断（推荐）

修改 `main.py`：

```python
import os
from dotenv import load_dotenv

load_dotenv()

# 根据环境变量选择 API
USE_OPENAI = os.environ.get("USE_OPENAI", "true").lower() == "true"

if USE_OPENAI:
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
    )
else:
    client = OpenAI(
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=os.environ.get("ARK_API_KEY"),
    )
```

然后在 `.env` 中添加：
```bash
USE_OPENAI=true  # 改为 false 切换到豆包
```

---

## 常见问题

### Q: 两个 API 可以同时使用吗？
A: 不能，需要手动切换配置。建议使用环境变量方法快速切换。

### Q: DALL-E API 有速率限制吗？
A: 有，根据你的账户等级不同：
- **Free tier**: 有限制
- **Pay-as-you-go**: 每分钟 5 张（DALL-E 3）

### Q: 为什么 API 固定使用 1024x1024？
A: 为了兼容性和稳定性：
- 所有模型都支持 1024x1024
- 生成后通过高质量算法缩放到目标尺寸
- 成本可控

### Q: 如何提高生成质量？
A: 几种方法：
1. 使用 DALL-E 3（比 DALL-E 2 质量更好）
2. 设置 `quality="hd"`（费用翻倍）
3. 优化提示词，提供更详细的描述
4. 在提示词中加入"高质量、高细节"等关键词

---

**最后更新时间：** 2025-12-08
