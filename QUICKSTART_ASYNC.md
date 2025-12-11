# 并发版本快速上手

## 🚀 5 分钟快速开始

### 1. 安装依赖（1 分钟）

```bash
cd /home/leke/playground/sysp-img-test/img-gen-tool
source venv/bin/activate
pip install aiohttp
```

### 2. 更新 MCP 配置（2 分钟）

编辑 Qwen Code 的 MCP 配置文件，将原有配置中的 `mcp_server.py` 改为 `mcp_server_async.py`：

```json
{
  "mcpServers": {
    "image-gen-tool": {
      "command": "/path/to/venv/bin/python",
      "args": [
        "/path/to/img-gen-tool/mcp_server_async.py"
      ],
      "timeout": 300000
    }
  }
}
```

### 3. 重启 Qwen Code（1 分钟）

重启 Qwen Code 使配置生效。

### 4. 测试生成（1 分钟）

在 Qwen Code 中：

```
请生成以下素材：
1. 红发女战士立绘
2. 蓝色能量剑道具
3. 森林场景背景
4. 生命值图标
5. 金币道具
```

等待生成完成，查看输出信息中的性能统计。

## 📊 预期结果

**串行版本：**
```
生成完成！
成功: 5 个
失败: 0 个
保存位置: ./public/assets/
总耗时: ~120-150s
```

**并发版本：**
```
🚀 并发生成完成！

📊 统计信息：
  • 成功: 5 个
  • 失败: 0 个
  • 总耗时: 45.2s
  • 平均耗时: 9.0s/张
  • 加速比: 2.8x (相比串行)
  • 保存位置: ./public/assets/
```

## 🎯 关键改进

1. **总耗时缩短 60-70%**
   - 从 120s 降到 45s
   - 加速比 2.8x

2. **更详细的性能统计**
   - 总耗时、平均耗时
   - 每张图像的处理时间
   - 加速比计算

3. **更友好的输出格式**
   - 使用 emoji 图标
   - 清晰的分组信息
   - 详细的进度提示

## 💡 优化建议

### 场景 1: 小批量生成（1-3 张）

```python
# 建议并发数：3
max_concurrent = 3
```

**原因：** 任务少，过高并发没有意义，反而增加开销。

### 场景 2: 中等批量（4-7 张）

```python
# 建议并发数：5（默认）
max_concurrent = 5
```

**原因：** 平衡速度和稳定性，最常用的配置。

### 场景 3: 大批量（8-15 张）

```python
# 建议并发数：8
max_concurrent = 8
```

**原因：** 充分利用并发，显著缩短总耗时。

### 场景 4: 超大批量（15+ 张）

```python
# 建议分批处理，每批 8-10 张
# 例如：20 张图像分 2-3 批执行
```

**原因：**
- 避免 API 限流
- 更好的错误控制
- 降低内存占用

## 🔧 常用调优

### 调整并发数

在 MCP 工具调用时指定：

```python
# Qwen Code 中调用（通常由 AI 自动处理）
generate_game_asset(workspace_dir, max_concurrent=8)
```

### 加速抠图处理

如果抠图成为瓶颈，在 `main_async.py` 中调整：

```python
BACKGROUND_REMOVAL_CONFIG = {
    "algorithm": "simple",  # 或减少 grabcut_iterations
    "grabcut_iterations": 3,  # 从 5 降到 3
    # ...
}
```

## 🐛 常见问题

### Q1: 安装 aiohttp 失败

```bash
# 尝试升级 pip
pip install --upgrade pip
pip install aiohttp
```

### Q2: 生成速度没有明显提升

**可能原因：**
1. 并发数设置过低（试试增加到 8）
2. 网络带宽不足
3. API 服务器响应慢

**解决方案：**
```bash
# 测试不同并发级别
# 在 Qwen Code 中尝试：
max_concurrent=3  # 测试
max_concurrent=5  # 测试
max_concurrent=8  # 测试
```

### Q3: 部分任务失败

**检查：**
1. API 配额是否充足
2. 网络连接是否稳定
3. 并发数是否过高（试试降低到 3）

## 📈 性能监控

每次生成后，查看输出中的性能指标：

```
📊 统计信息：
  • 总耗时: 45.2s          # 整个批次的总时间
  • 平均耗时: 9.0s/张       # 总耗时 / 任务数
  • 加速比: 2.8x           # 相比串行的提升
```

**理想指标：**
- 加速比 > 2.0x：并发效果良好
- 加速比 1.5-2.0x：有一定提升
- 加速比 < 1.5x：并发效果不明显，检查配置

## 🎓 进阶技巧

### 1. 混合使用串行和并发

```python
# 少量任务（1-3张）：使用串行版本
# - 稳定性高
# - 开销小

# 大量任务（5+张）：使用并发版本
# - 速度快
# - 适合批量生成
```

### 2. 动态调整并发数

```python
# 根据任务数量自动调整
if len(tasks) <= 3:
    max_concurrent = 3
elif len(tasks) <= 7:
    max_concurrent = 5
else:
    max_concurrent = 8
```

### 3. 错误重试策略

```python
# 如果部分任务失败
# 1. 查看错误详情
# 2. 降低并发数（从 8 降到 5）
# 3. 单独重试失败任务
```

## 🔄 回退到串行

如果遇到问题，随时可以回退：

1. 修改 MCP 配置：`mcp_server_async.py` → `mcp_server.py`
2. 重启 Qwen Code
3. 串行版本依然可用，只是速度较慢

## 📞 获取帮助

遇到问题？

1. 查看 `ASYNC_UPGRADE_GUIDE.md` 详细文档
2. 运行 `benchmark.py` 测试性能
3. 检查 API 配额和网络连接

---

**提示：** 并发版本在生成 5 张以上图像时效果最明显，建议批量生成时使用。
