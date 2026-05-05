import { importShared } from './__federation_fn_import-054b33c3.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-c4c0bc37.js';

const Config_vue_vue_type_style_index_0_scoped_92ad9a3f_lang = '';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "plugin-config" };

const {ref,reactive,onMounted} = await importShared('vue');


const PLUGIN_ID = 'NovaFram';

const _sfc_main = {
  __name: 'Config',
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

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_form = _resolveComponent("v-form");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
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
              icon: "mdi-cog",
              class: "mr-2",
              color: "white",
              size: "small"
            }),
            _cache[17] || (_cache[17] = _createElementVNode("span", { class: "text-white" }, "Nova农场配置", -1)),
            _createVNode(_component_v_spacer),
            _createVNode(_component_v_btn_group, {
              variant: "outlined",
              density: "compact",
              class: "mr-1"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_btn, {
                  color: "white",
                  onClick: switchToPage,
                  size: "small",
                  "min-width": "40",
                  class: "px-0 px-sm-3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-view-dashboard",
                      size: "18",
                      class: "mr-sm-1"
                    }),
                    _cache[13] || (_cache[13] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "状态页", -1))
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "white",
                  onClick: resetConfig,
                  disabled: saving.value,
                  size: "small",
                  "min-width": "40",
                  class: "px-0 px-sm-3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-restore",
                      size: "18",
                      class: "mr-sm-1"
                    }),
                    _cache[14] || (_cache[14] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "重置", -1))
                  ]),
                  _: 1
                }, 8, ["disabled"]),
                _createVNode(_component_v_btn, {
                  color: "white",
                  onClick: saveConfig,
                  loading: saving.value,
                  size: "small",
                  "min-width": "40",
                  class: "px-0 px-sm-3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-content-save",
                      size: "18",
                      class: "mr-sm-1"
                    }),
                    _cache[15] || (_cache[15] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "保存", -1))
                  ]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode(_component_v_btn, {
                  color: "white",
                  onClick: closePlugin,
                  size: "small",
                  "min-width": "40",
                  class: "px-0 px-sm-3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_icon, {
                      icon: "mdi-close",
                      size: "18"
                    }),
                    _cache[16] || (_cache[16] = _createElementVNode("span", { class: "btn-text d-none d-sm-inline" }, "关闭", -1))
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
                  "onClick:close": _cache[0] || (_cache[0] = $event => (successMessage.value = ''))
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
                  "onClick:close": _cache[1] || (_cache[1] = $event => (errorMessage.value = ''))
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(errorMessage.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_v_form, {
              ref_key: "configForm",
              ref: configForm
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card, {
                  flat: "",
                  class: "mb-4 bg-blue-lighten-5"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_card_title, { class: "text-subtitle-2 pa-3" }, {
                      default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                        _createTextVNode("基础设置", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_card_text, { class: "pa-3" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_row, null, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_switch, {
                                  modelValue: config.enabled,
                                  "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.enabled) = $event)),
                                  label: "启用插件",
                                  color: "blue-darken-2"
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_switch, {
                                  modelValue: config.notify,
                                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.notify) = $event)),
                                  label: "启用通知",
                                  color: "blue-darken-2"
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_text_field, {
                                  modelValue: config.cron,
                                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.cron) = $event)),
                                  label: "定时任务 (Cron表达式)",
                                  hint: "例如: 0 8 * * * (每天早上8点执行)",
                                  "persistent-hint": "",
                                  density: "compact"
                                }, null, 8, ["modelValue"])
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
                _createVNode(_component_v_card, {
                  flat: "",
                  class: "mb-4 bg-blue-lighten-5"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_card_title, { class: "text-subtitle-2 pa-3" }, {
                      default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                        _createTextVNode("站点配置", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_card_text, { class: "pa-3" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_row, null, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_textarea, {
                                  modelValue: config.cookie,
                                  "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.cookie) = $event)),
                                  label: "Cookie",
                                  hint: "输入站点Cookie用于身份认证",
                                  "persistent-hint": "",
                                  rows: "3",
                                  density: "compact"
                                }, null, 8, ["modelValue"])
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
                _createVNode(_component_v_card, {
                  flat: "",
                  class: "mb-4 bg-blue-lighten-5"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_card_title, { class: "text-subtitle-2 pa-3" }, {
                      default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                        _createTextVNode("自动化设置", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_card_text, { class: "pa-3" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_row, null, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_switch, {
                                  modelValue: config.auto_plant,
                                  "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.auto_plant) = $event)),
                                  label: "自动种植/养殖",
                                  color: "blue-darken-2"
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_switch, {
                                  modelValue: config.auto_sell,
                                  "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.auto_sell) = $event)),
                                  label: "自动出售",
                                  color: "blue-darken-2"
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            (config.auto_sell)
                              ? (_openBlock(), _createBlock(_component_v_col, {
                                  key: 0,
                                  cols: "12"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_v_text_field, {
                                      modelValue: config.auto_sell_threshold,
                                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.auto_sell_threshold) = $event)),
                                      modelModifiers: { number: true },
                                      label: "自动出售盈利阈值 (%)",
                                      hint: "当盈利低于此值时不出售",
                                      "persistent-hint": "",
                                      type: "number",
                                      density: "compact"
                                    }, null, 8, ["modelValue"])
                                  ]),
                                  _: 1
                                }))
                              : _createCommentVNode("", true),
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_switch, {
                                  modelValue: config.expiry_sale_enabled,
                                  "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.expiry_sale_enabled) = $event)),
                                  label: "临期自动出售",
                                  color: "blue-darken-2"
                                }, null, 8, ["modelValue"])
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
                _createVNode(_component_v_card, {
                  flat: "",
                  class: "mb-4 bg-blue-lighten-5"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_card_title, { class: "text-subtitle-2 pa-3" }, {
                      default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                        _createTextVNode("高级设置", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_card_text, { class: "pa-3" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_row, null, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_col, { cols: "12" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_switch, {
                                  modelValue: config.use_proxy,
                                  "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.use_proxy) = $event)),
                                  label: "使用代理",
                                  color: "blue-darken-2"
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_v_col, {
                              cols: "12",
                              sm: "6"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_text_field, {
                                  modelValue: config.retry_count,
                                  "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.retry_count) = $event)),
                                  modelModifiers: { number: true },
                                  label: "重试次数",
                                  type: "number",
                                  min: "0",
                                  max: "10",
                                  density: "compact"
                                }, null, 8, ["modelValue"])
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_v_col, {
                              cols: "12",
                              sm: "6"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_text_field, {
                                  modelValue: config.retry_interval,
                                  "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.retry_interval) = $event)),
                                  modelModifiers: { number: true },
                                  label: "重试间隔 (秒)",
                                  type: "number",
                                  min: "1",
                                  max: "60",
                                  density: "compact"
                                }, null, 8, ["modelValue"])
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
            }, 512)
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
const ConfigComponent = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-92ad9a3f"]]);

export { ConfigComponent as default };
