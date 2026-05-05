# NovaFram 插件 - 手动构建教程

这是一份详细的步骤指南，教你如何从零开始手动构建 NovaFram 农场插件。

---

## 📋 前置要求

在开始之前，请确保你已安装：

- **Node.js** (v16+) 和 **npm** (v8+)
- **Python** (v3.8+)
- **Git** (可选，但推荐)
- **文本编辑器** (如 VS Code)

### 检查版本

```bash
# 检查 Node.js 版本
node --version

# 检查 npm 版本
npm --version

# 检查 Python 版本
python --version 或 python3 --version
```

---

## 🎯 步骤 1: 项目目录结构

首先，了解完整的项目结构：

```
novafram/
├── __init__.py                 # Python 后端主文件
├── package.json                # Node.js 依赖配置
├── vite.config.js              # Vite 构建配置
├── build-zip.js                # 打包脚本
├── requirements.txt            # Python 依赖
├── index.html                  # HTML 入口
├── README.md                   # 使用说明
├── DEV_README.md              # 开发说明
├── src/                        # 前端源代码目录
│   ├── main.js                # Vue 应用入口
│   ├── App.vue                # 主组件（本地测试用）
│   ├── components/
│   │   ├── Page.vue           # 农场状态显示页面
│   │   └── Config.vue         # 配置页面
│   └── utils/
│       └── request.js         # HTTP 请求工具
├── public/                    # 静态资源（图片、图标等）
└── dist/                      # 构建输出目录（自动生成）
```

---

## 🚀 步骤 2: 安装前端依赖

### 2.1 进入项目目录

```bash
cd /path/to/novafram
```

### 2.2 安装 Node.js 依赖

```bash
npm install
```

这会安装 `package.json` 中定义的所有依赖：
- **vue** (^3.3.4) - 前端框架
- **vuetify** (^3.3.15) - UI 组件库
- **echarts** (^5.6.0) - 图表库
- **@vitejs/plugin-vue** - Vite Vue 插件
- **@originjs/vite-plugin-federation** - 模块联邦支持
- **archiver** - ZIP 打包工具

等待安装完成后，会生成 `node_modules/` 目录和 `package-lock.json` 文件。

**预期输出：**
```
added XXX packages, and audited XXX packages in XXXs
```

---

## 🎨 步骤 3: 理解项目文件

### 3.1 后端文件 (`__init__.py`)

这是整个插件的核心，包含：

**关键类：`NovaFram`**
```python
class NovaFram(_PluginBase):
    plugin_name = "Vue-Nova农场"
    plugin_version = "1.0.0"
    DEFAULT_SITE_URL = "https://pt.novahd.top"
```

**关键方法：**
- `init_plugin()` - 初始化配置
- `get_api()` - 定义 API 接口
- `get_farm_data()` - 获取农场数据
- `_farm_task()` - 定时任务执行逻辑

### 3.2 前端组件

**App.vue - 本地开发主组件**
- 用于本地测试的容器
- 包含两个标签页：Page 和 Config
- 模拟 MoviePilot 主应用的 API 调用

**Page.vue - 农场状态页**
- 显示农场数据统计
- 提供一键种植、收获、出售按钮
- 实时更新农场状态

**Config.vue - 配置页面**
- Cookie 输入
- Cron 表达式配置
- 自动化设置选项

### 3.3 构建配置

**vite.config.js**
```javascript
federation({
    name: 'NovaFram',
    exposes: {
        './Page': './src/components/Page.vue',
        './Config': './src/components/Config.vue'
    },
    shared: { vue, vuetify }  // 共享库，避免重复加载
})
```

这使用了"模块联邦"技术，允许 MoviePilot 主应用动态加载这些组件。

---

## 🔧 步骤 4: 本地开发和测试

### 4.1 启动开发服务器

```bash
npm run dev
```

**输出示例：**
```
  VITE v4.4.9  ready in XXX ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

### 4.2 访问本地页面

打开浏览器访问：`http://localhost:5173`

你会看到：
- 一个 App.vue 容器，包含两个标签页
- "运行状态 (Page.vue)" - 显示农场操作界面
- "插件配置 (Config.vue)" - 显示配置表单

### 4.3 本地测试 API 调用

由于本地没有真实的后端，API 调用会失败。你可以：

**方案 A: 创建 Mock 后端**

创建 `mock-server.js`：
```javascript
const express = require('express');
const app = express();

app.use(express.json());

// Mock API
app.post('/api/config', (req, res) => {
  res.json({ success: true, msg: '配置保存成功' });
});

app.get('/api/status', (req, res) => {
  res.json({
    farm_status: {
      crops: [{ name: '小麦', state: 'ripe' }],
      animals: [{ name: '鸡', state: 'empty' }],
      warehouse: []
    }
  });
});

app.listen(3000, () => {
  console.log('Mock 服务器运行在 http://localhost:3000');
});
```

然后修改 `App.vue` 中的 `baseURL`：
```javascript
const baseURL = 'http://localhost:3000';
```

**方案 B: 直接在浏览器控制台测试**

```javascript
// 打开浏览器开发者工具 (F12)
// 在 Console 标签页运行：

fetch('http://localhost:3000/api/config', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ enabled: true })
}).then(r => r.json()).then(console.log);
```

### 4.4 停止开发服务器

按 `Ctrl+C` 停止开发服务器。

---

## 📦 步骤 5: 前端构建

### 5.1 构建生产版本

```bash
npm run build:web
```

这会：
1. 编译 Vue 组件为 JavaScript
2. 打包所有依赖
3. 生成 `dist/` 目录，包含以下文件：
   - `dist/assets/` - 编译后的 JS、CSS
   - `dist/remoteEntry.js` - 模块联邦入口

**输出示例：**
```
dist/assets/main-xxx.js          50.23 kB │ gzip: 15.67 kB
dist/assets/style-xxx.css        25.12 kB │ gzip: 5.23 kB
dist/remoteEntry.js              10.45 kB │ gzip: 3.12 kB

✓ built in 12.34s
```

### 5.2 检查构建结果

```bash
ls -la dist/
```

你应该看到：
```
total 256
drwxr-xr-x  3 user  staff    96  1月 15 10:30 .
drwxr-xr-x 15 user  staff   480  1月 15 10:30 ..
drwxr-xr-x  4 user  staff   128  1月 15 10:30 assets
-rw-r--r--  1 user  staff 10450  1月 15 10:30 remoteEntry.js
```

---

## 📮 步骤 6: 打包为 ZIP 文件

### 6.1 打包命令

```bash
npm run build
```

这会执行：
1. `npm run build:web` - 前端构建
2. `node build-zip.js` - 打包为 ZIP

**输出示例：**
```
✓ novafram.zip 已生成，大小: 250.45 KB
```

### 6.2 检查 ZIP 文件

```bash
ls -lh novafram.zip
```

应该看到类似：
```
-rw-r--r--  1 user  staff  250K  1月 15 10:35 novafram.zip
```

### 6.3 验证 ZIP 内容

```bash
# macOS/Linux
unzip -l novafram.zip

# Windows
tar -tf novafram.zip
```

应该包含：
```
Archive:  novafram.zip
  Length      Date    Time    Name
---------  ---------- -----   ----
     1234  2024-01-15 10:35   __init__.py
    12345  2024-01-15 10:35   dist/remoteEntry.js
    23456  2024-01-15 10:35   dist/assets/main-xxx.js
    34567  2024-01-15 10:35   dist/assets/style-xxx.css
```

---

## 🎬 步骤 7: 上传到 MoviePilot

### 7.1 访问 MoviePilot 管理页面

1. 打开 MoviePilot Web 界面
2. 导航到 **设置 → 插件管理**
3. 点击 **上传插件** 按钮

### 7.2 选择 ZIP 文件

选择刚刚生成的 `novafram.zip` 文件，点击上传。

### 7.3 重启 MoviePilot

上传完成后，重启 MoviePilot 应用：

```bash
# 如果是 Docker
docker restart moviepilot

# 如果是本地运行
# 停止应用后重新启动
```

### 7.4 在插件管理页面启用

1. 在插件列表中找到 **Nova农场**
2. 点击启用按钮
3. 进入配置页面，填写：
   - **Cookie**: 你的站点 Cookie
   - **定时任务**: `0 8 * * *` (每天早上8点)
4. 点击保存

---

## 🔍 步骤 8: 修改和定制

现在你已经学会了基本的构建流程，可以进行定制化开发。

### 8.1 修改网站地址

编辑 `__init__.py`：

```python
# 找到这一行：
DEFAULT_SITE_URL = "https://pt.novahd.top"

# 改为你的网址（如果需要）
DEFAULT_SITE_URL = "https://your-site.com"
```

### 8.2 修改插件信息

在 `__init__.py` 中修改元数据：

```python
plugin_name = "Vue-Nova农场"              # 插件名称
plugin_desc = "支持NovaHD站点农场..."      # 插件描述
plugin_version = "1.0.0"                # 版本号
plugin_author = "YourName"              # 作者名
author_url = "https://github.com/YourName"  # 作者链接
```

### 8.3 修改页面样式

编辑 `src/components/Page.vue` 和 `Config.vue`：

```vue
<!-- 改变按钮颜色 -->
<v-btn color="success">绿色按钮</v-btn>
<v-btn color="warning">警告按钮</v-btn>
<v-btn color="error">错误按钮</v-btn>
```

### 8.4 添加新的 API 接口

在 `__init__.py` 的 `get_api()` 方法中添加：

```python
{
    "path": "/my-endpoint",
    "endpoint": self._my_handler,
    "methods": ["POST"],
    "auth": "bear",
    "summary": "我的接口"
}

def _my_handler(self, payload: dict = None):
    """自定义接口处理"""
    return {"success": True, "msg": "成功"}
```

---

## 🐛 调试技巧

### 查看浏览器控制台

按 `F12` 打开浏览器开发者工具：
- **Console 标签页** - 查看 JavaScript 错误
- **Network 标签页** - 查看 API 请求
- **Elements 标签页** - 查看 HTML 结构

### 查看 MoviePilot 日志

```bash
# Docker 日志
docker logs -f moviepilot

# 本地日志
tail -f /path/to/moviepilot/logs/moviepilot.log
```

### 常见错误解决

**问题：npm install 失败**
```bash
# 清除缓存后重试
npm cache clean --force
npm install
```

**问题：Vite 构建失败**
```bash
# 检查 Node.js 版本
node --version

# 删除 node_modules 重新安装
rm -rf node_modules package-lock.json
npm install
```

**问题：ZIP 打包失败**
```bash
# 检查是否缺少 archiver
npm install archiver --save-dev

# 手动测试打包脚本
node build-zip.js
```

---

## 📚 完整流程总结

```bash
# 1. 进入项目
cd /path/to/novafram

# 2. 安装依赖
npm install

# 3. 本地开发（可选）
npm run dev
# 访问 http://localhost:5173

# 4. 构建前端
npm run build:web

# 5. 打包 ZIP
npm run build

# 6. 上传到 MoviePilot
# 在 MoviePilot 管理页面上传 novafram.zip

# 7. 重启应用
docker restart moviepilot  # 或本地重启

# 8. 在插件管理启用并配置
```

---

## 🎓 进阶开发

### 与 PlayLet 农场的区别分析

**PlayletFram** 的特点：
- 支持详细的农场数据解析（作物、动物、仓库、菜市场）
- 实现了复杂的自动化逻辑
- 支持价格趋势统计
- 实现了临期物品自动出售

**你可以参考 PlayletFram 来完善 NovaFram**：

1. **增强 API 解析**
   ```python
   def get_farm_data(self):
       # 类似 PlayletFram 那样详细解析 HTML
       # 支持农作物、动物、仓库、菜市场等
   ```

2. **实现自动化功能**
   ```python
   def _auto_worker(self):
       # 智能调度和自动化任务
   ```

3. **添加数据统计**
   ```python
   def _record_market_trend(self):
       # 记录价格趋势
   ```

---

## 📞 故障排除

如果构建或运行出现问题，请检查：

1. ✅ Node.js 版本 >= 16
2. ✅ npm 版本 >= 8
3. ✅ 所有依赖安装成功
4. ✅ `dist/` 目录已生成
5. ✅ `novafram.zip` 文件存在

---

**恭喜！🎉 你已经学会了如何从零构建 NovaFram 农场插件！**

如有任何问题，请参考项目中的其他文档或查看 MoviePilot 官方文档。
