<template>
  <div class="novafram-page">
    <!-- 确认对话框 -->
    <v-dialog v-model="showDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6 bg-blue-lighten-5 text-blue-darken-2">
          <v-icon icon="mdi-alert" class="mr-2" size="small"></v-icon>
          {{ dialogTitle }}
        </v-card-title>
        <v-card-text class="pa-4">
          {{ dialogMessage }}
          <div class="text-caption text-grey mt-2">此操作不可撤销。</div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey-darken-1" variant="text" @click="showDialog = false">取消</v-btn>
          <v-btn color="blue-darken-2" variant="elevated" @click="confirmAction" :loading="loading">确认</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-card flat class="rounded border">
      <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2" style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);">
        <v-icon icon="mdi-sprout" class="mr-2" color="white" size="small"></v-icon>
        <span class="text-white">Nova农场</span>
        <v-spacer></v-spacer>
        
        <!-- 操作按钮组 -->
        <v-btn-group variant="outlined" density="compact" class="mr-1">
          <v-btn color="white" @click="refreshData" :loading="loading" size="small">
            <v-icon icon="mdi-refresh" size="18"></v-icon>
          </v-btn>
          <v-btn color="white" @click="switchToConfig" size="small">
            <v-icon icon="mdi-cog" size="18"></v-icon>
          </v-btn>
          <v-btn color="white" @click="closePlugin" size="small">
            <v-icon icon="mdi-close" size="18"></v-icon>
          </v-btn>
        </v-btn-group>
      </v-card-title>
      
      <v-card-text class="px-3 py-3">
        <!-- 状态提示 -->
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

        <!-- 加载状态 -->
        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate color="blue-darken-2"></v-progress-circular>
          <p class="mt-2 text-caption">加载中...</p>
        </div>

        <!-- 内容区域 -->
        <div v-else>
          <v-row class="mb-4">
            <v-col cols="12" md="6">
              <v-card flat class="bg-blue-lighten-5 pa-3">
                <v-card-title class="text-subtitle-2 text-blue-darken-2">农场数据</v-card-title>
                <v-card-text>
                  <div class="text-body-2">
                    <p><strong>种植区:</strong> {{ farmData.crops?.length || 0 }} 个地块</p>
                    <p><strong>养殖区:</strong> {{ farmData.animals?.length || 0 }} 个地块</p>
                    <p><strong>仓库:</strong> {{ farmData.warehouse?.length || 0 }} 项物品</p>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="12" md="6">
              <v-card flat class="bg-blue-lighten-5 pa-3">
                <v-card-title class="text-subtitle-2 text-blue-darken-2">操作面板</v-card-title>
                <v-card-text>
                  <v-btn-group class="d-flex flex-column w-100" vertical>
                    <v-btn color="success" class="mb-2" @click="handlePlantAll">一键种植</v-btn>
                    <v-btn color="primary" class="mb-2" @click="handleHarvestAll">一键收获</v-btn>
                    <v-btn color="warning" @click="handleSellAll">一键出售</v-btn>
                  </v-btn-group>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <!-- 最后更新时间 -->
          <v-text class="text-caption text-grey">
            最后更新: {{ lastUpdateTime }}
          </v-text>
        </div>
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

const loading = ref(false);
const successMessage = ref('');
const errorMessage = ref('');
const lastUpdateTime = ref('未更新');
const showDialog = ref(false);
const dialogTitle = ref('');
const dialogMessage = ref('');
let pendingAction = null;

const farmData = reactive({
  crops: [],
  animals: [],
  warehouse: [],
  market: []
});

// 刷新数据
const refreshData = async () => {
  loading.value = true;
  try {
    const result = await apiClient.post(buildUrl('/refresh'), {});
    if (result && result.success) {
      successMessage.value = '数据刷新成功';
      lastUpdateTime.value = new Date().toLocaleTimeString();
      // 这里可以加载农场数据
    } else {
      errorMessage.value = result?.msg || '刷新失败，请检查插件状态';
    }
  } catch (error) {
    errorMessage.value = '刷新失败: ' + error.message;
  } finally {
    loading.value = false;
  }
};

// 一键种植
const handlePlantAll = () => {
  dialogTitle.value = '一键种植';
  dialogMessage.value = '确定要一键种植所有空闲地块吗?';
  pendingAction = async () => {
    loading.value = true;
    try {
      const result = await apiClient.post(buildUrl('/plant-all'), { type: 'crop' });
      successMessage.value = result?.msg || '种植成功';
    } catch (error) {
      errorMessage.value = '操作失败: ' + error.message;
    } finally {
      loading.value = false;
    }
  };
  showDialog.value = true;
};

// 一键收获
const handleHarvestAll = async () => {
  loading.value = true;
  try {
    const result = await apiClient.post(buildUrl('/harvest-all'), {});
    successMessage.value = result?.msg || '一键收获成功';
    await refreshData();
  } catch (error) {
    errorMessage.value = '收获失败: ' + error.message;
  } finally {
    loading.value = false;
  }
};

// 一键出售
const handleSellAll = () => {
  dialogTitle.value = '一键出售';
  dialogMessage.value = '确定要一键出售仓库中的所有物品吗?';
  pendingAction = async () => {
    loading.value = true;
    try {
      const result = await apiClient.post(buildUrl('/sell-all'), {});
      successMessage.value = result?.msg || '出售成功';
    } catch (error) {
      errorMessage.value = '出售失败: ' + error.message;
    } finally {
      loading.value = false;
    }
  };
  showDialog.value = true;
};

// 确认操作
const confirmAction = async () => {
  showDialog.value = false;
  if (pendingAction) {
    await pendingAction();
    pendingAction = null;
  }
};

// 切换到配置页
const switchToConfig = () => {
  emit('switch', 'config');
};

// 关闭插件
const closePlugin = () => {
  emit('close');
};

// 初始化
onMounted(() => {
  refreshData();
});
</script>

<style scoped>
.novafram-page {
  padding: 16px;
}

.rounded {
  border-radius: 8px;
}

.border {
  border: 1px solid #e0e0e0;
}
</style>
