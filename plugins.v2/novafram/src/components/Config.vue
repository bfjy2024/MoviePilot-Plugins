<template>
  <div class="plugin-config">
    <v-card flat class="rounded border">
      <!-- 标题区域 -->
      <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2" style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);">
        <v-icon icon="mdi-cog" class="mr-2" color="white" size="small"></v-icon>
        <span class="text-white">Nova农场配置</span>
        <v-spacer />

        <!-- 操作按钮组 -->
        <v-btn-group variant="outlined" density="compact" class="mr-1">
          <v-btn color="white" @click="switchToPage" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon icon="mdi-view-dashboard" size="18" class="mr-sm-1"></v-icon>
            <span class="btn-text d-none d-sm-inline">状态页</span>
          </v-btn>
          <v-btn color="white" @click="resetConfig" :disabled="saving" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon icon="mdi-restore" size="18" class="mr-sm-1"></v-icon>
            <span class="btn-text d-none d-sm-inline">重置</span>
          </v-btn>
          <v-btn color="white" @click="saveConfig" :loading="saving" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon icon="mdi-content-save" size="18" class="mr-sm-1"></v-icon>
            <span class="btn-text d-none d-sm-inline">保存</span>
          </v-btn>
          <v-btn color="white" @click="closePlugin" size="small" min-width="40" class="px-0 px-sm-3">
            <v-icon icon="mdi-close" size="18"></v-icon>
            <span class="btn-text d-none d-sm-inline">关闭</span>
          </v-btn>
        </v-btn-group>
      </v-card-title>
      
      <v-card-text class="px-3 py-3">
        <!-- 成功提示 -->
        <v-alert 
          v-if="successMessage" 
          type="success" 
          density="compact" 
          class="mb-2 text-caption"
          variant="elevated"
          closable
          @click:close="successMessage = ''"
        >
          {{ successMessage }}
        </v-alert>

        <!-- 错误提示 -->
        <v-alert 
          v-if="errorMessage" 
          type="error" 
          density="compact" 
          class="mb-2 text-caption"
          variant="elevated"
          closable
          @click:close="errorMessage = ''"
        >
          {{ errorMessage }}
        </v-alert>

        <!-- 配置表单 -->
        <v-form ref="configForm">
          <!-- 基础设置 -->
          <v-card flat class="mb-4 bg-blue-lighten-5">
            <v-card-title class="text-subtitle-2 pa-3">基础设置</v-card-title>
            <v-card-text class="pa-3">
              <v-row>
                <v-col cols="12">
                  <v-switch
                    v-model="config.enabled"
                    label="启用插件"
                    color="blue-darken-2"
                  ></v-switch>
                </v-col>
                <v-col cols="12">
                  <v-switch
                    v-model="config.notify"
                    label="启用通知"
                    color="blue-darken-2"
                  ></v-switch>
                </v-col>
                <v-col cols="12">
                  <v-text-field
                    v-model="config.cron"
                    label="定时任务 (Cron表达式)"
                    hint="例如: 0 8 * * * (每天早上8点执行)"
                    persistent-hint
                    density="compact"
                  ></v-text-field>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- Cookie配置 -->
          <v-card flat class="mb-4 bg-blue-lighten-5">
            <v-card-title class="text-subtitle-2 pa-3">站点配置</v-card-title>
            <v-card-text class="pa-3">
              <v-row>
                <v-col cols="12">
                  <v-textarea
                    v-model="config.cookie"
                    label="Cookie"
                    hint="输入站点Cookie用于身份认证"
                    persistent-hint
                    rows="3"
                    density="compact"
                  ></v-textarea>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- 自动化设置 -->
          <v-card flat class="mb-4 bg-blue-lighten-5">
            <v-card-title class="text-subtitle-2 pa-3">自动化设置</v-card-title>
            <v-card-text class="pa-3">
              <v-row>
                <v-col cols="12">
                  <v-switch
                    v-model="config.auto_plant"
                    label="自动种植/养殖"
                    color="blue-darken-2"
                  ></v-switch>
                </v-col>
                <v-col cols="12">
                  <v-switch
                    v-model="config.auto_sell"
                    label="自动出售"
                    color="blue-darken-2"
                  ></v-switch>
                </v-col>
                <v-col cols="12" v-if="config.auto_sell">
                  <v-text-field
                    v-model.number="config.auto_sell_threshold"
                    label="自动出售盈利阈值 (%)"
                    hint="当盈利低于此值时不出售"
                    persistent-hint
                    type="number"
                    density="compact"
                  ></v-text-field>
                </v-col>
                <v-col cols="12">
                  <v-switch
                    v-model="config.expiry_sale_enabled"
                    label="临期自动出售"
                    color="blue-darken-2"
                  ></v-switch>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- 高级设置 -->
          <v-card flat class="mb-4 bg-blue-lighten-5">
            <v-card-title class="text-subtitle-2 pa-3">高级设置</v-card-title>
            <v-card-text class="pa-3">
              <v-row>
                <v-col cols="12">
                  <v-switch
                    v-model="config.use_proxy"
                    label="使用代理"
                    color="blue-darken-2"
                  ></v-switch>
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    v-model.number="config.retry_count"
                    label="重试次数"
                    type="number"
                    min="0"
                    max="10"
                    density="compact"
                  ></v-text-field>
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    v-model.number="config.retry_interval"
                    label="重试间隔 (秒)"
                    type="number"
                    min="1"
                    max="60"
                    density="compact"
                  ></v-text-field>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>
        </v-form>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';

const props = defineProps({
  api: {
    type: Object,
    default: null
  },
  initialConfig: {
    type: Object,
    default: () => ({})
  }
});

const emit = defineEmits(['close', 'switch']);

const createDefaultApi = () => ({
  get: async (url) => {
    const res = await fetch(url);
    return res.json();
  },
  post: async (url, data) => {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return res.json();
  }
});

const apiClient = props.api || createDefaultApi();
const PLUGIN_ID = 'NovaFram';
const buildUrl = (path) => `/plugin/${PLUGIN_ID}${path}`;

const configForm = ref(null);
const saving = ref(false);
const successMessage = ref('');
const errorMessage = ref('');

const config = reactive({
  enabled: false,
  notify: true,
  cron: '0 8 * * *',
  cookie: '',
  auto_plant: false,
  auto_sell: false,
  auto_sell_threshold: 0,
  expiry_sale_enabled: false,
  use_proxy: false,
  retry_count: 3,
  retry_interval: 5
});

// 保存配置
const saveConfig = async () => {
  saving.value = true;
  try {
    const result = await apiClient.post(buildUrl('/config'), config);
    if (result && result.success) {
      successMessage.value = '配置保存成功';
    } else {
      errorMessage.value = result?.msg || '保存失败';
    }
  } catch (error) {
    errorMessage.value = '保存失败: ' + error.message;
  } finally {
    saving.value = false;
  }
};

// 重置配置
const resetConfig = () => {
  if (props.initialConfig) {
    Object.assign(config, props.initialConfig);
    successMessage.value = '配置已重置';
  }
};

// 切换到状态页
const switchToPage = () => {
  emit('switch', 'page');
};

// 关闭插件
const closePlugin = () => {
  emit('close');
};

// 初始化
onMounted(async () => {
  if (props.initialConfig && Object.keys(props.initialConfig).length > 0) {
    Object.assign(config, props.initialConfig);
    return;
  }

  try {
    const result = await apiClient.get(buildUrl('/config'));
    if (result && result.enabled !== undefined) {
      Object.assign(config, result);
    }
  } catch (error) {
    errorMessage.value = '加载配置失败: ' + error.message;
  }
});
</script>

<style scoped>
.plugin-config {
  padding: 16px;
}

.rounded {
  border-radius: 8px;
}

.border {
  border: 1px solid #e0e0e0;
}
</style>
