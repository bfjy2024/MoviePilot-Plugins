# NovaFram 插件 - 快速参考

## 🚀 5 分钟快速开始

```bash
# 1. 安装依赖
npm install

# 2. 一键构建
npm run build

# 3. 上传 novafram.zip 到 MoviePilot
```

---

## 📂 项目结构速查

| 文件/文件夹 | 用途 | 修改频率 |
|-----------|------|--------|
| `__init__.py` | Python 后端业务逻辑 | ⭐⭐⭐ 常改 |
| `src/components/Page.vue` | 农场状态页 UI | ⭐⭐⭐ 常改 |
| `src/components/Config.vue` | 配置页 UI | ⭐⭐ 偶改 |
| `vite.config.js` | 前端构建配置 | ⭐ 少改 |
| `package.json` | Node.js 依赖 | ⭐ 少改 |
| `build-zip.js` | 打包脚本 | ⭐ 不改 |

---

## 🔧 常用命令

```bash
# 安装依赖
npm install

# 本地开发（http://localhost:5173）
npm run dev

# 只构建前端
npm run build:web

# 完整构建（包括打包 ZIP）
npm run build

# 只打包 ZIP
node build-zip.js
```

---

## 📝 常见修改

### 改变网站地址

**文件：** `__init__.py`

```python
# 第 32 行
DEFAULT_SITE_URL = "https://pt.novahd.top"  # 改这里
```

### 改变插件名称

**文件：** `__init__.py`

```python
# 第 15-16 行
plugin_name = "Vue-Nova农场"                # 改名称
plugin_desc = "支持NovaHD站点农场..."       # 改描述
```

### 改变 UI 样式

**文件：** `src/components/Page.vue`

```vue
<!-- 改按钮颜色 -->
<v-btn color="blue-darken-2">蓝色</v-btn>
<v-btn color="success">绿色</v-btn>
<v-btn color="warning">黄色</v-btn>
<v-btn color="error">红色</v-btn>
```

### 添加新的 API

**文件：** `__init__.py`

```python
def get_api(self):
    return [
        # ... 其他接口
        {
            "path": "/my-new-api",
            "endpoint": self._my_handler,
            "methods": ["POST"],
            "auth": "bear"
        }
    ]

def _my_handler(self, payload: dict = None):
    return {"success": True, "msg": "成功"}
```

---

## 🐛 快速调试

### 查看构建输出
```bash
ls -la dist/
cat dist/remoteEntry.js | head -20
```

### 验证 ZIP 内容
```bash
unzip -l novafram.zip
```

### 查看 MoviePilot 日志
```bash
docker logs -f moviepilot | grep -i nova
```

---

## 📊 构建输出说明

```
dist/
├── assets/
│   ├── main-XXXXX.js         # 主应用逻辑（Vue + 业务代码）
│   └── style-XXXXX.css        # 样式表
└── remoteEntry.js             # 模块联邦入口（MoviePilot 会加载这个）
```

---

## ⚠️ 常见错误

| 错误 | 解决方案 |
|------|--------|
| `npm: command not found` | 安装 Node.js (从 nodejs.org) |
| `Cannot find module 'vue'` | 运行 `npm install` |
| `build-zip.js not found` | 确认在 novafram 目录中 |
| `403 Forbidden in MoviePilot` | Cookie 无效或过期 |
| `Cannot GET /farm.php` | 检查网址是否正确 |

---

## 🎯 开发流程

```
修改代码
    ↓
npm run build
    ↓
上传 novafram.zip
    ↓
MoviePilot 重启
    ↓
在插件管理启用
    ↓
测试功能
```

---

## 📚 更多信息

- **详细教程**: 见 [BUILD_GUIDE.md](BUILD_GUIDE.md)
- **使用说明**: 见 [README.md](README.md)
- **开发说明**: 见 [DEV_README.md](DEV_README.md)

---

**下一步：** 根据 [BUILD_GUIDE.md](BUILD_GUIDE.md) 中的步骤，进行手动构建。
