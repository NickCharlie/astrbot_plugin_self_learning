/**
 * 系统偏好设置 - Light/Dark 主题切换、壁纸上传、数据管理
 */
window.SystemSetting = {
  props: { app: Object },
  data() {
    return {
      currentTheme: localStorage.getItem("macos-theme") || "light",
      currentWallpaper:
        localStorage.getItem("macos-wallpaper") || "/static/img/bg.jpg",
      presetWallpapers: ["/static/img/bg.jpg"],
      // 学习功能开关
      pluginConfig: null,
      configLoading: false,
      savingConfigKey: null,
      // 数据管理
      dataStats: null,
      dataLoading: false,
      clearingCategory: null,
    };
  },
  computed: {
    isDark() {
      return this.currentTheme === "dark";
    },
    panelBg() {
      return this.isDark ? "#1c1c1e" : "#f5f5f7";
    },
    panelColor() {
      return this.isDark ? "#e0e0e0" : "#333";
    },
    cardBg() {
      return this.isDark ? "#2c2c2e" : "#fff";
    },
    cardBorder() {
      return this.isDark ? "#3a3a3c" : "#e5e5e5";
    },
    dividerColor() {
      return this.isDark ? "#3a3a3c" : "#f0f0f0";
    },
    learningFeatureToggles() {
      var cfg = this.pluginConfig || {};
      return [
        { key: "enable_message_capture", label: "消息抓取", desc: "收集用户与 Bot 消息，作为所有学习功能的数据来源", icon: "chat_bubble" },
        { key: "enable_style_learning", label: "对话风格学习", desc: "自动启动风格学习、表达模式与学习批次处理", icon: "style" },
        { key: "enable_jargon_learning", label: "黑话学习", desc: "启用黑话统计预筛、黑话挖掘和黑话上下文能力", icon: "translate" },
        { key: "enable_realtime_learning", label: "实时学习", desc: "收到消息后立即进行后台学习处理，会增加实时负载", icon: "bolt" },
        { key: "enable_realtime_llm_filter", label: "实时 LLM 筛选", desc: "对实时消息使用 LLM 筛选，关闭可减少模型调用", icon: "filter_alt" },
        { key: "enable_goal_driven_chat", label: "目标驱动对话", desc: "自动检测对话目标并维护阶段规划", icon: "flag" },
        { key: "enable_expression_patterns", label: "表达模式学习", desc: "学习并注入群聊表达习惯和常用句式", icon: "text_fields" },
        { key: "enable_ml_analysis", label: "机器学习分析", desc: "启用文本聚类、行为分析与强化记忆回放", icon: "analytics" },
        { key: "enable_memory_graph", label: "记忆图系统", desc: "启用记忆关系图相关能力", icon: "hub" },
        { key: "enable_knowledge_graph", label: "知识图谱", desc: "启用实体关系和知识图谱增强能力", icon: "schema" },
        { key: "enable_affection_system", label: "好感度学习", desc: "根据互动更新用户好感度数据", icon: "favorite" },
        { key: "enable_daily_mood", label: "每日情绪", desc: "按日更新 Bot 情绪状态", icon: "mood" },
      ].map(function (item) {
        item.enabled = cfg[item.key] !== false;
        return item;
      });
    },
    dataCategories() {
      var stats = this.dataStats || {};
      return [
        {
          key: "messages",
          label: "消息数据",
          desc: "原始消息、筛选消息、Bot 消息、对话上下文",
          icon: "chat_bubble",
          count: stats.messages || 0,
          endpoint: "/api/data/clear/messages",
        },
        {
          key: "persona_reviews",
          label: "人格审查",
          desc: "人格学习审查记录、人格备份",
          icon: "person_search",
          count: stats.persona_reviews || 0,
          endpoint: "/api/data/clear/persona_reviews",
        },
        {
          key: "style_learning",
          label: "对话风格学习",
          desc: "风格审查、表达模式、风格档案",
          icon: "style",
          count: stats.style_learning || 0,
          endpoint: "/api/data/clear/style_learning",
        },
        {
          key: "jargon",
          label: "黑话数据",
          desc: "黑话词条、使用频率记录",
          icon: "translate",
          count: stats.jargon || 0,
          endpoint: "/api/data/clear/jargon",
        },
        {
          key: "learning_history",
          label: "学习历史",
          desc: "学习批次、会话、强化反馈、优化日志",
          icon: "history",
          count: stats.learning_history || 0,
          endpoint: "/api/data/clear/learning_history",
        },
      ];
    },
    totalDataCount() {
      if (!this.dataStats) return 0;
      var s = this.dataStats;
      return (
        (s.messages || 0) +
        (s.persona_reviews || 0) +
        (s.style_learning || 0) +
        (s.jargon || 0) +
        (s.learning_history || 0)
      );
    },
  },
  mounted() {
    this.loadDataStatistics();
    this.loadPluginConfig();
  },
  methods: {
    setTheme(theme) {
      this.currentTheme = theme;
      localStorage.setItem("macos-theme", theme);
      document.documentElement.setAttribute("data-theme", theme);
      document.body.setAttribute("data-theme", theme);
      if (theme === "dark") {
        document.body.style.colorScheme = "dark";
      } else {
        document.body.style.colorScheme = "light";
      }
    },
    setWallpaper(url) {
      this.currentWallpaper = url;
      localStorage.setItem("macos-wallpaper", url);
      window.EventBus.emit("wallpaper-change", url);
    },
    triggerUpload() {
      if (this.$refs.fileInput) {
        this.$refs.fileInput.click();
      }
    },
    uploadWallpaper(event) {
      var file = event.target.files[0];
      if (!file) return;
      if (!file.type.startsWith("image/")) {
        alert("请选择图片文件");
        return;
      }
      var reader = new FileReader();
      reader.onload = (e) => {
        this.setWallpaper(e.target.result);
      };
      reader.readAsDataURL(file);
    },

    // ── 学习功能开关 ────────────────────────────────

    async loadPluginConfig() {
      this.configLoading = true;
      try {
        var api = window.MacOSApi;
        var result = api ? await api.get("/api/config") : await fetch("/api/config", { credentials: "include" }).then(function (resp) { return resp.json(); });
        this.pluginConfig = result.data || result;
      } catch (e) {
        console.error("[SystemSetting] loadPluginConfig error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("加载学习功能开关失败: " + e.message);
        }
      } finally {
        this.configLoading = false;
      }
    },

    async toggleLearningFeature(item) {
      if (!this.pluginConfig || this.savingConfigKey) return;
      var nextValue = !item.enabled;
      var oldConfig = Object.assign({}, this.pluginConfig);
      this.pluginConfig[item.key] = nextValue;
      this.savingConfigKey = item.key;
      try {
        var patch = {};
        patch[item.key] = nextValue;
        var api = window.MacOSApi;
        var result = api ? await api.post("/api/config", patch) : await fetch("/api/config", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        }).then(function (resp) { return resp.json(); });
        var data = result.data || result;
        this.pluginConfig = data.new_config || data;
        if (typeof ElMessage !== "undefined") {
          ElMessage.success(item.label + (nextValue ? "已启用" : "已关闭"));
        }
      } catch (e) {
        this.pluginConfig = oldConfig;
        console.error("[SystemSetting] toggleLearningFeature error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("保存失败: " + e.message);
        }
      } finally {
        this.savingConfigKey = null;
      }
    },

    // ── 数据管理 ──────────────────────────────────

    async loadDataStatistics() {
      this.dataLoading = true;
      try {
        var resp = await fetch("/api/data/statistics", {
          credentials: "include",
        });
        if (resp.ok) {
          var body = await resp.json();
          if (body.success && body.data) {
            this.dataStats = body.data;
          }
        }
      } catch (e) {
        console.error("[SystemSetting] loadDataStatistics error:", e);
      } finally {
        this.dataLoading = false;
      }
    },

    async clearCategory(cat) {
      try {
        if (typeof ElMessageBox !== "undefined") {
          await ElMessageBox.confirm(
            "确定要清空「" +
              cat.label +
              "」的全部 " +
              cat.count +
              " 条数据吗？此操作不可撤销。",
            "清空确认",
            {
              confirmButtonText: "确认清空",
              cancelButtonText: "取消",
              type: "warning",
            },
          );
        }
      } catch (e) {
        return;
      }

      this.clearingCategory = cat.key;
      try {
        var resp = await fetch(cat.endpoint, {
          method: "DELETE",
          credentials: "include",
        });
        var body = await resp.json().catch(function () {
          return {};
        });
        if (resp.ok && body.success) {
          if (typeof ElMessage !== "undefined") {
            ElMessage.success(body.message || "已清空");
          }
          await this.loadDataStatistics();
        } else {
          if (typeof ElMessage !== "undefined") {
            ElMessage.error("清空失败: " + (body.message || "未知错误"));
          }
        }
      } catch (e) {
        console.error("[SystemSetting] clearCategory error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("清空失败: " + e.message);
        }
      } finally {
        this.clearingCategory = null;
      }
    },

    async clearAllData() {
      try {
        if (typeof ElMessageBox !== "undefined") {
          await ElMessageBox.confirm(
            "确定要清空所有插件数据吗？包括消息、人格审查、对话风格、黑话、学习历史等全部数据。此操作不可撤销！",
            "一键清空所有数据",
            {
              confirmButtonText: "确认清空全部",
              cancelButtonText: "取消",
              type: "warning",
              confirmButtonClass: "el-button--danger",
            },
          );
        }
      } catch (e) {
        return;
      }

      this.clearingCategory = "all";
      try {
        var resp = await fetch("/api/data/clear/all", {
          method: "DELETE",
          credentials: "include",
        });
        var body = await resp.json().catch(function () {
          return {};
        });
        if (resp.ok && body.success) {
          if (typeof ElMessage !== "undefined") {
            ElMessage.success(body.message || "已清空全部数据");
          }
          await this.loadDataStatistics();
        } else {
          if (typeof ElMessage !== "undefined") {
            ElMessage.error("清空失败: " + (body.message || "未知错误"));
          }
        }
      } catch (e) {
        console.error("[SystemSetting] clearAllData error:", e);
        if (typeof ElMessage !== "undefined") {
          ElMessage.error("清空失败: " + e.message);
        }
      } finally {
        this.clearingCategory = null;
      }
    },
  },
  template: `
    <div :style="{width:'100%',height:'100%',overflowY:'auto',padding:'24px',boxSizing:'border-box',textShadow:'none',color:panelColor,background:panelBg}">
      <h3 style="margin:0 0 20px 0;font-size:16px;font-weight:600;">外观</h3>
      <div style="display:flex;gap:16px;margin-bottom:30px;">
        <div @click="setTheme('light')"
             :style="{cursor:'pointer',padding:'12px',borderRadius:'12px',border: currentTheme==='light' ? '2px solid #007aff' : '2px solid '+cardBorder,background:cardBg,textAlign:'center',width:'120px'}">
          <div style="height:60px;background:linear-gradient(180deg,#f5f5f7,#fff);border-radius:8px;margin-bottom:8px;border:1px solid #e5e5e5;"></div>
          <div style="font-size:13px;font-weight:500;">浅色</div>
        </div>
        <div @click="setTheme('dark')"
             :style="{cursor:'pointer',padding:'12px',borderRadius:'12px',border: currentTheme==='dark' ? '2px solid #007aff' : '2px solid '+cardBorder,background:cardBg,textAlign:'center',width:'120px'}">
          <div style="height:60px;background:linear-gradient(180deg,#1c1c1e,#2c2c2e);border-radius:8px;margin-bottom:8px;border:1px solid #e5e5e5;"></div>
          <div style="font-size:13px;font-weight:500;">深色</div>
        </div>
      </div>

      <h3 style="margin:0 0 20px 0;font-size:16px;font-weight:600;">桌面壁纸</h3>
      <div style="margin-bottom:16px;">
        <button type="button" @click="triggerUpload" style="display:inline-flex;align-items:center;gap:8px;padding:8px 16px;background:#007aff;color:#fff;border-radius:8px;cursor:pointer;font-size:13px;border:none;font-family:inherit;">上传壁纸</button>
        <input type="file" accept="image/*" ref="fileInput" @change="uploadWallpaper" style="position:absolute;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;" />
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <div v-for="wp in presetWallpapers" :key="wp" @click="setWallpaper(wp)"
             :style="{width:'140px',height:'90px',borderRadius:'8px',backgroundImage:'url('+wp+')',backgroundSize:'cover',backgroundPosition:'center',cursor:'pointer',border: currentWallpaper===wp ? '3px solid #007aff' : '3px solid transparent'}">
        </div>
      </div>

      <!-- 学习功能开关 -->
      <h3 style="margin:30px 0 16px 0;font-size:16px;font-weight:600;">学习功能开关</h3>
      <div v-if="configLoading" style="padding:16px 0;font-size:13px;color:#86868b;">
        加载学习功能配置中...
      </div>
      <div v-else :style="{background:cardBg,borderRadius:'10px',border:'1px solid '+cardBorder,overflow:'hidden'}">
        <div v-for="(item, idx) in learningFeatureToggles" :key="item.key"
             :style="{display:'flex',alignItems:'center',justifyContent:'space-between',gap:'16px',padding:'12px 16px',borderTop: idx > 0 ? '1px solid '+dividerColor : 'none'}">
          <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0;">
            <i class="material-icons" :style="{fontSize:'20px',color:item.enabled ? '#007aff' : '#86868b'}">{{ item.icon }}</i>
            <div style="min-width:0;">
              <div style="font-size:13px;font-weight:500;">{{ item.label }}</div>
              <div style="font-size:11px;color:#86868b;margin-top:2px;">{{ item.desc }}</div>
            </div>
          </div>
          <button type="button"
                  @click="toggleLearningFeature(item)"
                  :disabled="!pluginConfig || savingConfigKey !== null"
                  :style="{
                    width:'46px',height:'26px',padding:'2px',borderRadius:'13px',border:'none',flexShrink:0,
                    cursor: !pluginConfig || savingConfigKey !== null ? 'not-allowed' : 'pointer',
                    background: item.enabled ? '#34c759' : (isDark ? '#3a3a3c' : '#d1d1d6'),
                    opacity: savingConfigKey === item.key ? 0.6 : 1,
                    transition:'background .2s ease',
                  }">
            <span :style="{
              display:'block',width:'22px',height:'22px',borderRadius:'50%',background:'#fff',
              transform: item.enabled ? 'translateX(20px)' : 'translateX(0)',
              transition:'transform .2s ease',boxShadow:'0 1px 3px rgba(0,0,0,.25)',
            }"></span>
          </button>
        </div>
      </div>

      <!-- 数据管理 -->
      <h3 style="margin:30px 0 16px 0;font-size:16px;font-weight:600;">数据管理</h3>
      <div v-if="dataLoading" style="padding:16px 0;font-size:13px;color:#86868b;">
        加载统计数据中...
      </div>
      <div v-else>
        <div :style="{background:cardBg,borderRadius:'10px',border:'1px solid '+cardBorder,overflow:'hidden'}">
          <div v-for="(cat, idx) in dataCategories" :key="cat.key"
               :style="{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'12px 16px',borderTop: idx > 0 ? '1px solid '+dividerColor : 'none'}">
            <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0;">
              <i class="material-icons" :style="{fontSize:'20px',color:'#86868b'}">{{ cat.icon }}</i>
              <div style="min-width:0;">
                <div style="font-size:13px;font-weight:500;">{{ cat.label }}</div>
                <div style="font-size:11px;color:#86868b;margin-top:2px;">{{ cat.desc }}</div>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:12px;flex-shrink:0;">
              <span style="font-size:12px;color:#86868b;font-variant-numeric:tabular-nums;">{{ cat.count }} 条</span>
              <button type="button"
                      @click="clearCategory(cat)"
                      :disabled="cat.count === 0 || clearingCategory !== null"
                      :style="{
                        display:'inline-flex',alignItems:'center',gap:'4px',
                        padding:'5px 12px',borderRadius:'6px',cursor: cat.count === 0 || clearingCategory !== null ? 'not-allowed' : 'pointer',
                        fontSize:'12px',border:'none',fontFamily:'inherit',
                        background: cat.count === 0 ? (isDark ? '#3a3a3c' : '#e5e5e5') : '#ff3b30',
                        color: cat.count === 0 ? '#86868b' : '#fff',
                        opacity: clearingCategory === cat.key ? 0.6 : 1,
                      }">
                <i class="material-icons" style="font-size:14px;">{{ clearingCategory === cat.key ? 'hourglass_empty' : 'delete_outline' }}</i>
                {{ clearingCategory === cat.key ? '清空中...' : '清空' }}
              </button>
            </div>
          </div>
        </div>

        <!-- 一键清空全部 -->
        <div style="margin-top:12px;display:flex;align-items:center;justify-content:space-between;">
          <div style="font-size:12px;color:#86868b;">
            共 {{ totalDataCount }} 条数据
          </div>
          <button type="button"
                  @click="clearAllData()"
                  :disabled="totalDataCount === 0 || clearingCategory !== null"
                  :style="{
                    display:'inline-flex',alignItems:'center',gap:'6px',
                    padding:'8px 18px',borderRadius:'8px',
                    cursor: totalDataCount === 0 || clearingCategory !== null ? 'not-allowed' : 'pointer',
                    fontSize:'13px',fontWeight:'500',border:'none',fontFamily:'inherit',
                    background: totalDataCount === 0 ? (isDark ? '#3a3a3c' : '#e5e5e5') : '#ff3b30',
                    color: totalDataCount === 0 ? '#86868b' : '#fff',
                    opacity: clearingCategory === 'all' ? 0.6 : 1,
                  }">
            <i class="material-icons" style="font-size:16px;">{{ clearingCategory === 'all' ? 'hourglass_empty' : 'delete_forever' }}</i>
            {{ clearingCategory === 'all' ? '清空中...' : '一键清空全部数据' }}
          </button>
        </div>
      </div>

      <h3 style="margin:30px 0 16px 0;font-size:16px;font-weight:600;">关于</h3>
      <div :style="{padding:'12px 16px',background:cardBg,borderRadius:'10px',border:'1px solid '+cardBorder}">
        <div style="display:flex;justify-content:space-between;padding:6px 0;font-size:13px;">
          <span style="color:#86868b;">QQ 交流群</span>
          <a href="https://qm.qq.com/q/1021544792" target="_blank" style="color:#007aff;text-decoration:none;">1021544792</a>
        </div>
        <div :style="{display:'flex',justifyContent:'space-between',padding:'6px 0',fontSize:'13px',borderTop:'1px solid '+dividerColor}">
          <span style="color:#86868b;">GitHub</span>
          <a href="https://github.com/NickCharlie/astrbot_plugin_self_learning" target="_blank" style="color:#007aff;text-decoration:none;">查看仓库</a>
        </div>
      </div>
    </div>
  `,
};
