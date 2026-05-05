import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const Page_vue_vue_type_style_index_0_scoped_83a44fb0_lang = '';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "novafram-page" };
const _hoisted_2 = {
  key: 2,
  class: "text-center py-6"
};
const _hoisted_3 = { key: 3 };
const _hoisted_4 = { class: "text-body-2" };

const {ref,reactive,onMounted} = await importShared('vue');


const PLUGIN_ID = 'NovaFram';

const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    default: null
  },
  initialConfig: {
    type: Object,
    default: () => ({})
  }
},
  emits: ['close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

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

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_dialog = _resolveComponent("v-dialog");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_progress_circular = _resolveComponent("v-progress-circular");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_text = _resolveComponent("v-text");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_dialog, {
      modelValue: showDialog.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((showDialog).value = $event)),
      "max-width": "400"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, { class: "text-h6 bg-blue-lighten-5 text-blue-darken-2" }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, {
                  icon: "mdi-alert",
                  class: "mr-2",
                  size: "small"
                }),
                _createTextVNode(" " + _toDisplayString(dialogTitle.value), 1)
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_text, { class: "pa-4" }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(dialogMessage.value) + " ", 1),
                _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-caption text-grey mt-2" }, "此操作不可撤销。", -1))
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  color: "grey-darken-1",
                  variant: "text",
                  onClick: _cache[0] || (_cache[0] = $event => (showDialog.value = false))
                }, {
                  default: _withCtx(() => [...(_cache[5] || (_cache[5] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "blue-darken-2",
                  variant: "elevated",
                  onClick: confirmAction,
                  loading: loading.value
                }, {
                  default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
                    _createTextVNode("确认", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_card, {
      flat: "",
      class: "rounded border"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, {
          class: "text-subtitle-1 d-flex align-center px-3 py-2",
          style: {"background":"linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)"}
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-sprout",
              class: "mr-2",
              color: "white",
              size: "small"
            }),
            _cache[7] || (_cache[7] = _createElementVNode("span", { class: "text-white" }, "Nova农场", -1)),
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_btn_group, {
              variant: "outlined",
              density: "compact",
              class: "mr-1"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_btn, {
                  color: "white",
                  onClick: refreshData,
                  loading: loading.value,
                  size: "small"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-refresh",
                      size: "18"
                    })
                  ]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode(_component_v_btn, {
                  color: "white",
                  onClick: switchToConfig,
                  size: "small"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-cog",
                      size: "18"
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "white",
                  onClick: closePlugin,
                  size: "small"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-close",
                      size: "18"
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_v_card_text, { class: "px-3 py-3" }, {
          default: _withCtx(() => [
            (successMessage.value)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "success",
                  density: "compact",
                  class: "mb-2 text-caption",
                  variant: "elevated",
                  closable: "",
                  "onClick:close": _cache[2] || (_cache[2] = $event => (successMessage.value = ''))
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(successMessage.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            (errorMessage.value)
              ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 1,
                  type: "error",
                  density: "compact",
                  class: "mb-2 text-caption",
                  variant: "elevated",
                  closable: "",
                  "onClick:close": _cache[3] || (_cache[3] = $event => (errorMessage.value = ''))
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(errorMessage.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            (loading.value)
              ? (_openBlock(), _createElementBlock("div", _hoisted_2, [
                  _createVNode(_component_v_progress_circular, {
                    indeterminate: "",
                    color: "blue-darken-2"
                  }),
                  _cache[8] || (_cache[8] = _createElementVNode("p", { class: "mt-2 text-caption" }, "加载中...", -1))
                ]))
              : (_openBlock(), _createElementBlock("div", _hoisted_3, [
                  _createVNode(_component_v_row, { class: "mb-4" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_col, {
                        cols: "12",
                        md: "6"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card, {
                            flat: "",
                            class: "bg-blue-lighten-5 pa-3"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_card_title, { class: "text-subtitle-2 text-blue-darken-2" }, {
                                default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                                  _createTextVNode("农场数据", -1)
                                ]))]),
                                _: 1
                              }),
                              _createVNode(_component_v_card_text, null, {
                                default: _withCtx(() => [
                                  _createElementVNode("div", _hoisted_4, [
                                    _createElementVNode("p", null, [
                                      _cache[10] || (_cache[10] = _createElementVNode("strong", null, "种植区:", -1)),
                                      _createTextVNode(" " + _toDisplayString(farmData.crops?.length || 0) + " 个地块", 1)
                                    ]),
                                    _createElementVNode("p", null, [
                                      _cache[11] || (_cache[11] = _createElementVNode("strong", null, "养殖区:", -1)),
                                      _createTextVNode(" " + _toDisplayString(farmData.animals?.length || 0) + " 个地块", 1)
                                    ]),
                                    _createElementVNode("p", null, [
                                      _cache[12] || (_cache[12] = _createElementVNode("strong", null, "仓库:", -1)),
                                      _createTextVNode(" " + _toDisplayString(farmData.warehouse?.length || 0) + " 项物品", 1)
                                    ])
                                  ])
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "12",
                        md: "6"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card, {
                            flat: "",
                            class: "bg-blue-lighten-5 pa-3"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_card_title, { class: "text-subtitle-2 text-blue-darken-2" }, {
                                default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
                                  _createTextVNode("操作面板", -1)
                                ]))]),
                                _: 1
                              }),
                              _createVNode(_component_v_card_text, null, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_btn_group, {
                                    class: "d-flex flex-column w-100",
                                    vertical: ""
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_btn, {
                                        color: "success",
                                        class: "mb-2",
                                        onClick: handlePlantAll
                                      }, {
                                        default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                                          _createTextVNode("一键种植", -1)
                                        ]))]),
                                        _: 1
                                      }),
                                      _createVNode(_component_v_btn, {
                                        color: "primary",
                                        class: "mb-2",
                                        onClick: handleHarvestAll
                                      }, {
                                        default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
                                          _createTextVNode("一键收获", -1)
                                        ]))]),
                                        _: 1
                                      }),
                                      _createVNode(_component_v_btn, {
                                        color: "warning",
                                        onClick: handleSellAll
                                      }, {
                                        default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                                          _createTextVNode("一键出售", -1)
                                        ]))]),
                                        _: 1
                                      })
                                    ]),
                                    _: 1
                                  })
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_text, { class: "text-caption text-grey" }, {
                    default: _withCtx(() => [
                      _createTextVNode(" 最后更新: " + _toDisplayString(lastUpdateTime.value), 1)
                    ]),
                    _: 1
                  })
                ]))
          ]),
          _: 1
        })
      ]),
      _: 1
    })
  ]))
}
}

};
const PageComponent = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-83a44fb0"]]);

export { PageComponent as default };
