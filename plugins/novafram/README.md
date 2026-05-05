# NovaFram 插件

支持 NovaHD 站点农场的 MoviePilot 插件

## 功能特性

- 🌱 一键种植/养殖
- 🎯 一键收获
- 💰 一键出售
- ⏰ 定时自动化
- 📊 实时数据展示
- 🔧 灵活配置

## 安装说明

1. 将 `novafram.zip` 上传到 MoviePilot 插件管理页面
2. 重启 MoviePilot 应用
3. 在插件设置中配置 Cookie 和 Cron 表达式

## 配置说明

### 基础设置
- **启用插件**: 打开/关闭插件功能
- **启用通知**: 任务完成后是否发送通知
- **定时任务**: Cron 表达式，例如 `0 8 * * *` 表示每天早上 8 点执行

### 站点配置
- **Cookie**: 从浏览器获取站点 Cookie

### 自动化设置
- **自动种植/养殖**: 自动完成种植和收获循环
- **自动出售**: 自动出售仓库中的物品
- **盈利阈值**: 仅当盈利超过此百分比时才出售
- **临期自动出售**: 自动出售即将过期的物品

### 高级设置
- **使用代理**: 是否使用代理访问
- **重试次数**: 请求失败的重试次数
- **重试间隔**: 重试之间的等待时间

## 开发说明

### 项目结构
```
novafram/
├── __init__.py           # 后端 Python 代码
├── package.json          # 前端依赖
├── vite.config.js        # Vite 配置
├── build-zip.js          # 打包脚本
├── index.html            # 入口 HTML
└── src/
    ├── main.js           # 前端入口
    ├── App.vue           # 主组件
    ├── components/
    │   ├── Page.vue      # 状态展示页
    │   └── Config.vue    # 配置页
    └── utils/
        └── request.js    # HTTP 请求工具
```

### 开发流程
```bash
# 1. 安装依赖
npm install

# 2. 开发模式
npm run dev

# 3. 构建
npm run build
```

## 变更历史

### v1.0.0 (2024-01-01)
- 初始版本发布

## 许可证

MIT
