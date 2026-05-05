<template>
  <v-app>
    <v-app-bar color="blue-darken-2" app>
      <v-app-bar-title>Nova农场 - 本地测试环境</v-app-bar-title>
      <v-spacer></v-spacer>
      <v-chip color="white" variant="outlined" size="small">开发模式</v-chip>
    </v-app-bar>

    <v-main>
      <v-container>
        <v-tabs v-model="tab" color="blue-darken-2" class="mb-4">
          <v-tab value="page">运行状态 (Page.vue)</v-tab>
          <v-tab value="config">插件配置 (Config.vue)</v-tab>
        </v-tabs>

        <v-window v-model="tab">
          <v-window-item value="page">
            <PageComponent 
              :api="apiWrapper"
              :initial-config="pluginConfig"
              @close="handleClose('Page')"
              @switch="switchTab"
            />
          </v-window-item>
          
          <v-window-item value="config">
            <ConfigComponent 
              :api="apiWrapper"
              :initial-config="pluginConfig"
              @close="handleClose('Config')"
              @switch="switchTab"
            />
          </v-window-item>
        </v-window>
      </v-container>
    </v-main>

    <!-- 全局通知 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>
  </v-app>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import PageComponent from './components/Page.vue';
import ConfigComponent from './components/Config.vue';
import { createRequest } from './utils/request';

// 当前激活的标签页
const tab = ref('page');

// 插件配置
const pluginConfig = reactive({
  enabled: false,
  notify: true,
  cron: '',
  cookie: ''
});

// 全局通知
const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
});

// 创建 API 包装器
const baseURL = 'http://localhost:3000';
const request = createRequest(baseURL);

// API 包装器
const apiWrapper = {
  get: async (url, config) => {
    try {
      const res = await request.get(url, config);
      return res;
    } catch (error) {
      console.error('GET请求失败:', url, error);
      showNotification(`请求失败: ${error.message}`, 'error');
      throw error;
    }
  },
  post: async (url, data, config) => {
    try {
      const res = await request.post(url, data, config);
      return res;
    } catch (error) {
      console.error('POST请求失败:', url, error);
      showNotification(`请求失败: ${error.message}`, 'error');
      throw error;
    }
  }
};

// 显示通知
const showNotification = (message, type = 'success') => {
  snackbar.message = message;
  snackbar.color = type;
  snackbar.show = true;
};

// 处理关闭
const handleClose = (component) => {
  console.log(`${component} 已关闭`);
};

// 切换标签页
const switchTab = (tabName) => {
  tab.value = tabName;
};

// 初始化
onMounted(() => {
  console.log('App.vue 已加载');
});
</script>

<style scoped>
.bg-gradient-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
</style>
