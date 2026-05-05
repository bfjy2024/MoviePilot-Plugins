# NovaFram 开发环境

这个 App.vue 是一个本地开发环境模拟器

## 启动步骤

1. 安装依赖:
```bash
npm install
```

2. 启动开发服务器:
```bash
npm run dev
```

3. 打开浏览器访问 http://localhost:5173

## 说明

- Page.vue 是农场状态页面，展示农场数据和操作按钮
- Config.vue 是配置页面，用于设置 Cookie 和其他参数
- 在生产环境中，这些组件会被 MoviePilot 主应用以模块联邦的方式动态加载

## 后端开发

如果你需要在本地测试后端，请创建一个简单的 Flask 服务器:

```python
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    return jsonify({
        'enabled': True,
        'notify': True,
        'cron': '0 8 * * *'
    })

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'enabled': True,
        'farm_status': {}
    })

if __name__ == '__main__':
    app.run(debug=True, port=3000)
```

然后修改 App.vue 中的 baseURL 为 `http://localhost:3000`
