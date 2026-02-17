# Elysia-Nonebot Skills 使用文档

这是一套为 Elysia-Nonebot 项目设计的 Claude Code skills，用于快速执行常用的开发和运维操作。

## 📋 Skills 列表

### 🚀 基本运行操作 (5个)

| Skill | 功能 | 说明 |
|-------|------|------|
| `bot-start` | 启动机器人 | 启动 Nonebot2 主程序，包括 Flask 后端和定时任务 |
| `bot-stop` | 停止机器人 | 优雅地停止机器人进程 |
| `bot-restart` | 重启机器人 | 平滑重启（等待4秒完成当前操作） |
| `bot-logs` | 查看日志 | 查看主日志或错误日志，支持实时跟踪 |
| `bot-status` | 查看状态 | 检查进程、后端、数据库、磁盘空间等 |

### 🔧 开发调试工具 (2个)

| Skill | 功能 | 说明 |
|-------|------|------|
| `plugin-list` | 列出插件 | 显示所有已安装插件及其功能 |
| `test-plugin` | 测试插件 | 测试指定插件的基本功能 |

### 💾 数据库和配置管理 (4个)

| Skill | 功能 | 说明 |
|-------|------|------|
| `db-backup` | 备份数据库 | 备份 SQLite 数据库，保留最近7天 |
| `db-init` | 初始化数据库 | 创建或重建数据库表结构 |
| `db-query` | 查询数据库 | 执行 SQL 查询，查看表结构 |
| `config-check` | 检查配置 | 验证所有配置文件是否正确 |

### 📦 依赖和环境管理 (3个)

| Skill | 功能 | 说明 |
|-------|------|------|
| `deps-install` | 安装依赖 | 安装 Python 和 Node.js 依赖 |
| `deps-update` | 更新依赖 | 更新 Python 依赖到最新版本 |
| `clean-cache` | 清理缓存 | 清理临时文件、视频缓存、旧日志 |

## 🎯 使用方法

### 在 Claude Code 中使用

1. **基本用法**: 直接输入 skill 名称
   ```
   /bot-start
   /bot-status
   /plugin-list
   ```

2. **带参数的 skill**: 使用 `--` 指定参数
   ```
   /bot-logs --tail 100
   /bot-logs --errors
   /db-query .tables
   /db-query SELECT * FROM users
   ```

3. **需要确认的 skill**: 系统会提示你确认
   ```
   /bot-stop
   /bot-restart
   /clean-cache
   ```

## 📖 常见使用场景

### 场景 1: 首次部署

```bash
# 1. 检查配置
/config-check

# 2. 安装依赖
/deps-install

# 3. 初始化数据库
/db-init

# 4. 启动机器人
/bot-start

# 5. 查看状态
/bot-status
```

### 场景 2: 更新代码后

```bash
# 1. 停止机器人（可选）
/bot-stop

# 2. 拉取最新代码
git pull

# 3. 更新依赖（如果需要）
/deps-update

# 4. 重启机器人
/bot-restart

# 5. 查看日志确认
/bot-logs --tail 50
```

### 场景 3: 日常维护

```bash
# 1. 查看运行状态
/bot-status

# 2. 备份数据库
/db-backup

# 3. 清理缓存
/clean-cache

# 4. 查看日志
/bot-logs --tail 100
```

### 场景 4: 故障排查

```bash
# 1. 检查运行状态
/bot-status

# 2. 查看错误日志
/bot-logs --errors

# 3. 检查配置
/config-check

# 4. 测试插件
/test-plugin <plugin_name>
```

## ⚙️ Skill 详细说明

### bot-start

启动 Elysia Bot 主程序。

**功能**:
- 创建 PID 文件
- 初始化数据库连接
- 启动 Flask 后端（端口 5001）
- 启动定时任务（每2小时自动重启、每日0点清理缓存）

**使用场景**:
- 首次启动
- 更新代码后重新启动
- 手动停止后恢复运行

### bot-stop

优雅地停止机器人进程。

**功能**:
- 读取 bot.pid 获取进程 ID
- 使用 SIGTERM 信号终止进程
- 自动关闭数据库连接

**注意事项**:
- 如果进程无响应，可能需要手动终止
- PID 文件不会被删除

### bot-restart

平滑重启机器人。

**功能**:
- 等待 4 秒让原进程完成当前操作
- 终止原进程
- 等待 5 秒确保完全关闭
- 启动新进程并更新 PID

**注意事项**:
- 这是一个平滑重启，会尽量减少服务中断
- 系统已配置每2小时自动重启

### bot-logs

查看机器人运行日志。

**参数**:
- `--tail N`: 显示最后 N 行（默认 50）
- `--errors`: 只显示错误日志
- `--follow`: 实时跟踪日志

**示例**:
```bash
/bot-logs --tail 100    # 查看最后100行
/bot-logs --errors       # 只看错误
/bot-logs --follow       # 实时跟踪（Ctrl+C 退出）
```

### bot-status

检查机器人运行状态。

**检查项**:
- 进程是否运行
- Flask 后端是否可访问
- 数据库文件是否存在
- 最近的错误日志
- 磁盘空间使用情况

### plugin-list

列出所有已安装的插件及其功能。

**输出信息**:
- 插件名称
- 功能描述
- 相关指令

**插件列表**:
- check.py - 指令路由
- chat.py - AI聊天管理
- weather.py - 天气查询
- fortune.py - 今日运势、塔罗牌
- to_do.py - 待办事项
- cloud_music.py - 网易云音乐
- bili_vid_search.py - B站视频搜索
- 等 24 个插件...

### test-plugin

测试指定插件的功能。

**使用方法**:
```bash
/test-plugin weather       # 测试天气插件
/test-plugin chat          # 测试聊天插件
```

**注意事项**:
- 需要先启动机器人
- 某些插件需要额外配置

### db-backup

备份 SQLite 数据库。

**功能**:
- 复制 chat_bot.db 到备份目录
- 文件名带时间戳
- 自动保留最近 7 天的备份
- 清理超过 7 天的旧备份

**备份位置**: `src/resources/backups/`

### db-init

初始化或重新初始化数据库。

**功能**:
- 创建所有数据表
- 可选择保留数据或清空数据
- 验证表结构

**数据表**:
- users - 用户信息
- admin_list - 管理员列表
- ban_list - 黑名单
- chat - AI聊天记录
- to_do - 待办事项
- fortune - 运势记录
- tarot - 塔罗牌数据
- questions - 问答数据

**注意事项**:
- ⚠️ 清空数据不可逆，请先备份

### db-query

查询 SQLite 数据库。

**命令**:
- `.tables` - 查看所有表
- `.schema <表名>` - 查看表结构
- `<SQL查询>` - 执行SQL查询

**示例**:
```bash
/db-query .tables                          # 查看所有表
/db-query .schema users                    # 查看 users 表结构
/db-query SELECT * FROM users LIMIT 10     # 查询前10个用户
/db-query SELECT COUNT(*) FROM to_do       # 统计待办数量
```

### config-check

检查所有配置文件是否正确。

**检查项**:
- .env.prod 是否存在且配置正确
- api_config.py 是否从 example 创建
- QQ 机器人配置（ID、token、secret）
- API 密钥配置
- 路径配置是否正确
- 依赖文件是否存在
- 数据库文件

**使用场景**:
- 启动前检查
- 故障排查
- 部署验证

### deps-install

安装所有必需的依赖。

**功能**:
1. 安装 Python 依赖: `pip install -r requirements_Elysia.txt`
2. 安装 Node.js 依赖: `npm install`
3. 验证安装是否成功

**使用场景**:
- 首次部署
- 依赖更新
- 环境迁移

**注意事项**:
- 需要 Python 3.11/3.12
- 需要 Node.js 环境（用于网易云音乐）
- 建议使用虚拟环境

### deps-update

更新 Python 依赖到最新版本。

**功能**:
- 更新所有依赖或指定依赖
- 生成更新报告

**示例**:
```bash
/deps-update              # 更新所有依赖
/deps-update nonebot2     # 只更新 nonebot2
```

**注意事项**:
- 更新可能带来兼容性问题
- 建议先在测试环境验证

### clean-cache

清理临时文件和缓存。

**清理目录**:
- src/resources/temp/ - 临时文件
- src/resources/videos/ - 视频缓存
- src/clover_music/yuc_wiki_path/ - Wiki缓存
- 旧日志文件（超过7天）

**注意事项**:
- ⚠️ 清理操作不可逆
- 临时文件会被永久删除
- 建议先备份数据库

## 🔍 故障排查

### 问题: 机器人无法启动

**解决步骤**:
1. 检查配置: `/config-check`
2. 查看日志: `/bot-logs --errors`
3. 检查依赖: `/deps-install`
4. 查看状态: `/bot-status`

### 问题: 机器人运行异常

**解决步骤**:
1. 查看状态: `/bot-status`
2. 查看错误日志: `/bot-logs --errors`
3. 重启机器人: `/bot-restart`
4. 如果还不行，尝试: `/bot-stop` 然后 `/bot-start`

### 问题: 数据库错误

**解决步骤**:
1. 先备份: `/db-backup`
2. 检查数据库: `/db-query .tables`
3. 如果损坏，重建: `/db-init`
4. 恢复备份（如需要）

### 问题: 磁盘空间不足

**解决步骤**:
1. 清理缓存: `/clean-cache`
2. 查看空间: `/bot-status`
3. 清理旧备份

## 📚 相关文件

### 配置文件
- `.env.prod` - 环境配置
- `src/configs/api_config.py` - API配置
- `src/configs/path_config.py` - 路径配置
- `pyproject.toml` - 项目配置

### 依赖文件
- `requirements_Elysia.txt` - Python依赖
- `package.json` - Node.js依赖

### 日志文件
- `src/resources/log/log.log` - 主日志
- `src/resources/log/error.log` - 错误日志

### 数据库
- `chat_bot.db` - SQLite数据库
- `src/resources/backups/` - 数据库备份

## 🎓 最佳实践

1. **定期备份**: 每天或每次重大操作前执行 `/db-backup`
2. **监控日志**: 定期查看 `/bot-logs` 了解运行状况
3. **检查状态**: 使用 `/bot-status` 进行健康检查
4. **清理缓存**: 每周执行一次 `/clean-cache`
5. **更新依赖**: 谨慎更新，先测试再部署
6. **配置检查**: 启动前执行 `/config-check`

## 🤝 贡献

如果你有新的 skill 想法或改进建议，欢迎提交！

## 📄 许可

与 Elysia-Nonebot 项目相同。

---

**Happy Coding! 🚀**
