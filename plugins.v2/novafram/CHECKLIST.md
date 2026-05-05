# NovaFram 构建检查清单

## ✅ 项目文件验证

运行以下命令验证所有文件都已成功创建：

```bash
# 进入 novafram 目录
cd /path/to/novafram

# 验证所有必需文件
ls -la

# 应该看到以下文件：
# - __init__.py          (Python 后端)
# - package.json         (Node.js 配置)
# - vite.config.js       (Vite 配置)
# - build-zip.js         (打包脚本)
# - index.html           (HTML 入口)
# - requirements.txt     (Python 依赖)
# - src/                 (Vue 源代码)
# - public/              (静态资源)
# - dist/                (构建输出)
```

## 📂 完整目录结构检查

```bash
# 检查 src 目录
ls -la src/
# 应该包括：App.vue, main.js, components/, utils/

# 检查 src/components
ls -la src/components/
# 应该包括：Page.vue, Config.vue

# 检查 src/utils
ls -la src/utils/
# 应该包括：request.js
```

## 🔧 前置条件检查

```bash
# 检查 Node.js
node --version
# 应该 >= v16.0.0

# 检查 npm
npm --version
# 应该 >= v8.0.0

# 检查 Python
python --version 或 python3 --version
# 应该 >= 3.8
```

## 📝 手动构建步骤

### 步骤 1: 安装依赖

```bash
cd /path/to/novafram
npm install
```

✅ **验证**: 应该看到类似输出：
```
added XXX packages, and audited XXX packages
```

### 步骤 2: 本地开发测试 (可选)

```bash
npm run dev
```

✅ **验证**: 
- 输出应该显示 `Local: http://localhost:5173/`
- 访问该地址应该看到 App.vue 界面

按 `Ctrl+C` 停止。

### 步骤 3: 前端构建

```bash
npm run build:web
```

✅ **验证**: 
- 应该看到构建完成信息
- `dist/` 目录应该包含 `assets/` 和 `remoteEntry.js`

### 步骤 4: 打包 ZIP

```bash
npm run build
```

✅ **验证**:
- 输出应该显示 `✓ novafram.zip 已生成`
- `novafram.zip` 文件应该存在

### 步骤 5: 验证 ZIP 内容

```bash
# macOS/Linux
unzip -l novafram.zip | head -20

# Windows
tar -tf novafram.zip | head -20
```

✅ **验证**:
- 应该包含 `__init__.py`
- 应该包含 `dist/remoteEntry.js`
- 应该包含 `dist/assets/` 目录

## 📊 构建结果检查

```bash
# 检查 ZIP 文件大小
ls -lh novafram.zip

# 应该在 50-300 KB 之间
```

## 🎯 上传检查清单

上传前，请确保：

- [ ] `novafram.zip` 文件存在
- [ ] 文件大小 > 50 KB
- [ ] ZIP 中包含 `__init__.py`
- [ ] ZIP 中包含 `dist/` 目录
- [ ] 文件名正确为 `novafram.zip`

## 📱 上传步骤

1. [ ] 进入 MoviePilot Web 界面
2. [ ] 导航到 **设置 → 插件管理**
3. [ ] 点击 **上传插件** 按钮
4. [ ] 选择 `novafram.zip` 文件
5. [ ] 点击上传
6. [ ] 重启 MoviePilot 应用

## ✨ 启用与配置

1. [ ] 在插件列表中找到 **Nova农场**
2. [ ] 点击启用按钮
3. [ ] 进入配置页面
4. [ ] 填写 **Cookie**: (从浏览器获取)
5. [ ] 填写 **定时任务**: `0 8 * * *`
6. [ ] 点击保存
7. [ ] 访问农场页面测试

## 🧪 功能测试

测试以下功能是否正常：

- [ ] 插件在插件列表中显示
- [ ] 配置页面可以打开
- [ ] 农场状态页面可以打开
- [ ] "一键种植" 按钮响应
- [ ] "一键收获" 按钮响应
- [ ] "一键出售" 按钮响应
- [ ] 刷新数据正常工作
- [ ] 定时任务在指定时间执行

## 🐛 故障排除

### 问题 1: npm install 失败

```bash
# 清除缓存并重试
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

### 问题 2: 构建失败

```bash
# 检查 Node 版本
node --version  # 应 >= 16

# 检查 npm 版本
npm --version   # 应 >= 8

# 尝试重新安装
npm install --force
npm run build
```

### 问题 3: ZIP 文件创建失败

```bash
# 检查 archiver 是否安装
npm install archiver --save-dev

# 手动测试打包
node build-zip.js
```

### 问题 4: 上传到 MoviePilot 失败

- 确认 ZIP 文件完整
- 检查 MoviePilot 磁盘空间
- 查看 MoviePilot 日志获取错误信息

### 问题 5: 插件启用后无效

- 确认 Cookie 正确有效
- 查看 MoviePilot 插件日志
- 尝试重启 MoviePilot

## 📚 文档快速导航

| 文档 | 用途 |
|------|------|
| [BUILD_GUIDE.md](BUILD_GUIDE.md) | 详细构建教程 |
| [QUICK_START.md](QUICK_START.md) | 快速参考 |
| [SUMMARY.md](SUMMARY.md) | 总体总结 |
| [README.md](README.md) | 项目说明 |
| [DEV_README.md](DEV_README.md) | 开发说明 |

## ✅ 最终检查

在提交使用前，请确保：

- [x] 所有源代码文件已创建
- [x] 依赖配置正确
- [x] 前端组件完整
- [x] Python 后端基础功能实现
- [x] 构建脚本可执行
- [x] ZIP 打包成功
- [x] 文档完善

**🎉 一切就绪！可以进行构建了！**

---

## 🚀 立即开始

```bash
# 一键构建
cd /path/to/novafram
npm install
npm run build

# 然后按照"上传步骤"上传到 MoviePilot
```

---

**需要帮助？** 查看 [BUILD_GUIDE.md](BUILD_GUIDE.md) 的详细说明。
