/**
 * 人格管理 - Persona Management App
 * CRUD management for persona profiles with card grid, dialogs, import/export.
 * Auto-refreshes every 30 seconds.
 */
window.AppPersonaManagement = {
  props: { app: Object },

  template: `
    <div class="app-content">
      <!-- Loading State -->
      <div v-if="loading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载人格列表中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <template v-else>

        <!-- ========== Header: Title + Action Buttons ========== -->
        <div class="section-card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
          <h3 style="margin:0;display:flex;align-items:center;">
            <i class="material-icons" style="font-size:18px;margin-right:6px;color:#34c759;">person</i>
            人格管理
          </h3>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <el-button type="primary" size="small" @click="openCreateDialog">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;">add</i>
              创建人格
            </el-button>
            <el-button size="small" @click="openImportDialog">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;">file_upload</i>
              导入人格
            </el-button>
            <el-button size="small" @click="refreshAll" :loading="refreshing">
              <i class="material-icons" style="font-size:14px;vertical-align:-2px;margin-right:3px;" v-if="!refreshing">refresh</i>
              刷新列表
            </el-button>
          </div>
        </div>

        <!-- ========== Personas Grid ========== -->
        <div v-if="personas.length > 0" class="persona-grid" style="margin-bottom:12px;">
          <el-card v-for="persona in personas" :key="persona.persona_id"
                   shadow="hover"
                   :body-style="{ padding: '16px' }"
                   style="border-radius:10px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
              <div style="display:flex;align-items:center;gap:6px;">
                <i class="material-icons" style="font-size:20px;color:#34c759;">person</i>
                <span style="font-size:14px;font-weight:600;color:#1d1d1f;">{{ persona.persona_id }}</span>
              </div>
              <span v-if="defaultPersona && defaultPersona.persona_id === persona.persona_id"
                    style="font-size:10px;padding:2px 8px;border-radius:10px;background:#d1e7dd;color:#0f5132;font-weight:500;">
                当前激活
              </span>
            </div>

            <div style="font-size:12px;color:#86868b;line-height:1.6;min-height:48px;margin-bottom:12px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;">
              {{ truncateText(persona.system_prompt, 150) || '(无系统提示词)' }}
            </div>

            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <el-button size="small" @click="openEditDialog(persona.persona_id)">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">edit</i>
                编辑
              </el-button>
              <el-button size="small" @click="exportPersona(persona.persona_id)">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">file_download</i>
                导出
              </el-button>
              <el-button size="small" type="danger" @click="deletePersona(persona.persona_id)">
                <i class="material-icons" style="font-size:13px;vertical-align:-2px;margin-right:2px;">delete</i>
                删除
              </el-button>
            </div>
          </el-card>
        </div>

        <!-- Empty State -->
        <div v-else class="empty-state" style="margin-bottom:12px;">
          <i class="material-icons">person_off</i>
          <p>暂无人格配置，请点击"创建人格"开始</p>
        </div>

        <!-- ========== Default Persona Section ========== -->
        <div class="section-card">
          <h3>
            <i class="material-icons" style="font-size:16px;vertical-align:text-bottom;margin-right:4px;color:#007aff;">star</i>
            当前激活人格
          </h3>
          <div v-if="defaultPersona">
            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #f0f0f0;">
              <span style="font-size:12px;color:#86868b;">人格ID</span>
              <span style="font-size:13px;font-weight:600;color:#1d1d1f;">{{ defaultPersona.persona_id }}</span>
            </div>
            <div style="padding:10px 0;border-bottom:1px solid #f0f0f0;">
              <div style="font-size:12px;color:#86868b;margin-bottom:4px;">系统提示词</div>
              <div style="font-size:12px;color:#1d1d1f;line-height:1.6;max-height:120px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;background:#f9f9fb;padding:8px;border-radius:6px;">{{ defaultPersona.system_prompt || '(空)' }}</div>
            </div>
            <div style="display:flex;gap:16px;padding:8px 0;">
              <div style="flex:1;">
                <span style="font-size:12px;color:#86868b;">开场对话数</span>
                <div style="font-size:14px;font-weight:600;color:#1d1d1f;margin-top:2px;">{{ getArrayLength(defaultPersona.begin_dialogs) }}</div>
              </div>
              <div style="flex:1;">
                <span style="font-size:12px;color:#86868b;">工具数</span>
                <div style="font-size:14px;font-weight:600;color:#1d1d1f;margin-top:2px;">{{ getArrayLength(defaultPersona.tools) }}</div>
              </div>
            </div>
          </div>
          <div v-else style="text-align:center;padding:16px;color:#86868b;font-size:12px;">
            暂无激活的人格配置
          </div>
        </div>

        <!-- ========== Create/Edit Dialog ========== -->
        <el-dialog
          :title="dialogMode === 'create' ? '创建人格' : '编辑人格'"
          v-model="dialogVisible"
          width="640px"
          :close-on-click-modal="false"
          destroy-on-close>
          <div style="display:flex;flex-direction:column;gap:16px;">

            <!-- persona_id -->
            <div>
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">人格ID</label>
              <el-input
                v-model="form.persona_id"
                :disabled="dialogMode === 'edit'"
                placeholder="请输入人格ID，如: default, assistant_v2"
                clearable />
              <div v-if="dialogMode === 'edit'" style="font-size:11px;color:#86868b;margin-top:4px;">编辑模式下人格ID不可修改</div>
            </div>

            <!-- system_prompt -->
            <div>
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">系统提示词 (System Prompt)</label>
              <el-input
                v-model="form.system_prompt"
                type="textarea"
                :autosize="{ minRows: 6, maxRows: 16 }"
                placeholder="请输入系统提示词，用于定义人格的角色、性格和行为模式..."
                resize="vertical" />
            </div>

            <!-- begin_dialogs -->
            <div>
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">开场对话 (Begin Dialogs) - JSON格式</label>
              <el-input
                v-model="form.begin_dialogs"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 10 }"
                placeholder='JSON数组格式，例如:
[
  {"role": "user", "content": "你好"},
  {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}
]'
                resize="vertical" />
              <div style="font-size:11px;color:#86868b;margin-top:4px;">JSON数组，每个元素包含 role 和 content 字段</div>
            </div>

            <!-- tools -->
            <div>
              <label style="font-size:13px;font-weight:500;color:#1d1d1f;display:block;margin-bottom:6px;">工具列表 (Tools) - JSON格式</label>
              <el-input
                v-model="form.tools"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 8 }"
                placeholder='JSON数组格式，例如: [{"name": "search", "description": "搜索工具"}]'
                resize="vertical" />
              <div style="font-size:11px;color:#86868b;margin-top:4px;">JSON数组，定义人格可使用的工具</div>
            </div>

          </div>

          <template #footer>
            <div style="display:flex;justify-content:flex-end;gap:8px;">
              <el-button @click="dialogVisible = false">取消</el-button>
              <el-button type="primary" @click="savePersona" :loading="saving">
                {{ dialogMode === 'create' ? '创建' : '保存' }}
              </el-button>
            </div>
          </template>
        </el-dialog>

        <!-- ========== Import Dialog ========== -->
        <el-dialog
          title="导入人格"
          v-model="importDialogVisible"
          width="460px"
          :close-on-click-modal="false"
          destroy-on-close>
          <div style="display:flex;flex-direction:column;align-items:center;gap:16px;padding:12px 0;">
            <i class="material-icons" style="font-size:48px;color:#007aff;opacity:0.7;">cloud_upload</i>
            <p style="font-size:13px;color:#86868b;margin:0;text-align:center;">选择一个 .json 文件导入人格配置</p>
            <input
              ref="importFileInput"
              type="file"
              accept=".json,application/json"
              @change="handleImportFile"
              style="font-size:13px;" />
          </div>

          <template #footer>
            <div style="display:flex;justify-content:flex-end;gap:8px;">
              <el-button @click="importDialogVisible = false">取消</el-button>
              <el-button type="primary" @click="submitImport" :loading="importing" :disabled="!importFile">
                导入
              </el-button>
            </div>
          </template>
        </el-dialog>

        <!-- ========== Social Links Footer ========== -->
        <div class="social-links">
          <a class="qq-link" href="https://qm.qq.com/q/1021544792" target="_blank" rel="noopener">QQ群: 1021544792</a>
          <a class="gh-link" href="https://github.com/NickCharlie/astrbot_plugin_self_learning" target="_blank" rel="noopener">GitHub</a>
        </div>

      </template>
    </div>
  `,

  data() {
    return {
      loading: true,
      refreshing: false,
      saving: false,
      importing: false,

      personas: [],
      defaultPersona: null,

      // Create/Edit dialog
      dialogVisible: false,
      dialogMode: 'create', // 'create' or 'edit'
      form: {
        persona_id: '',
        system_prompt: '',
        begin_dialogs: '',
        tools: '',
      },

      // Import dialog
      importDialogVisible: false,
      importFile: null,

      // Auto-refresh timer
      refreshTimer: null,
    };
  },

  methods: {
    /* ---------- Data Loading ---------- */
    async loadPersonas() {
      try {
        var resp = await fetch('/api/persona_management/list');
        var data = await resp.json();
        this.personas = (data && data.personas) ? data.personas : [];
      } catch (e) {
        console.error('[PersonaManagement] Failed to load personas:', e);
        ElementPlus.ElMessage.error('加载人格列表失败: ' + (e.message || '网络错误'));
      }
    },

    async loadDefaultPersona() {
      try {
        var resp = await fetch('/api/persona_management/default');
        var data = await resp.json();
        this.defaultPersona = data || null;
      } catch (e) {
        console.error('[PersonaManagement] Failed to load default persona:', e);
        this.defaultPersona = null;
      }
    },

    async refreshAll() {
      this.refreshing = true;
      try {
        await Promise.all([this.loadPersonas(), this.loadDefaultPersona()]);
      } finally {
        this.refreshing = false;
      }
    },

    /* ---------- Truncation Utility ---------- */
    truncateText(text, maxLen) {
      if (!text) return '';
      if (text.length <= maxLen) return text;
      return text.substring(0, maxLen) + '...';
    },

    getArrayLength(arr) {
      if (Array.isArray(arr)) return arr.length;
      if (typeof arr === 'string') {
        try {
          var parsed = JSON.parse(arr);
          return Array.isArray(parsed) ? parsed.length : 0;
        } catch (e) {
          return 0;
        }
      }
      return 0;
    },

    /* ---------- Create Dialog ---------- */
    openCreateDialog() {
      this.dialogMode = 'create';
      this.form = {
        persona_id: '',
        system_prompt: '',
        begin_dialogs: '[]',
        tools: '[]',
      };
      this.dialogVisible = true;
    },

    /* ---------- Edit Dialog ---------- */
    async openEditDialog(personaId) {
      this.dialogMode = 'edit';
      this.form = {
        persona_id: personaId,
        system_prompt: '',
        begin_dialogs: '[]',
        tools: '[]',
      };
      this.dialogVisible = true;

      try {
        var resp = await fetch('/api/persona_management/get/' + encodeURIComponent(personaId));
        var data = await resp.json();
        if (data) {
          this.form.persona_id = data.persona_id || personaId;
          this.form.system_prompt = data.system_prompt || '';
          this.form.begin_dialogs = Array.isArray(data.begin_dialogs)
            ? JSON.stringify(data.begin_dialogs, null, 2)
            : (data.begin_dialogs || '[]');
          this.form.tools = Array.isArray(data.tools)
            ? JSON.stringify(data.tools, null, 2)
            : (data.tools || '[]');
        }
      } catch (e) {
        console.error('[PersonaManagement] Failed to load persona details:', e);
        ElementPlus.ElMessage.error('加载人格详情失败: ' + (e.message || '网络错误'));
      }
    },

    /* ---------- Save (Create / Update) ---------- */
    async savePersona() {
      // Validate persona_id
      if (!this.form.persona_id || !this.form.persona_id.trim()) {
        ElementPlus.ElMessage.error('请输入人格ID');
        return;
      }

      // Validate JSON fields
      var beginDialogs, tools;
      try {
        beginDialogs = this.form.begin_dialogs.trim() ? JSON.parse(this.form.begin_dialogs) : [];
      } catch (e) {
        ElementPlus.ElMessage.error('开场对话 JSON 格式无效，请检查');
        return;
      }
      try {
        tools = this.form.tools.trim() ? JSON.parse(this.form.tools) : [];
      } catch (e) {
        ElementPlus.ElMessage.error('工具列表 JSON 格式无效，请检查');
        return;
      }

      this.saving = true;
      try {
        var payload = {
          persona_id: this.form.persona_id.trim(),
          system_prompt: this.form.system_prompt,
          begin_dialogs: JSON.stringify(beginDialogs),
          tools: JSON.stringify(tools),
        };

        var url = this.dialogMode === 'create'
          ? '/api/persona_management/create'
          : '/api/persona_management/update/' + encodeURIComponent(this.form.persona_id);

        var resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        var result = await resp.json();

        if (resp.ok) {
          ElementPlus.ElMessage.success(this.dialogMode === 'create' ? '人格创建成功' : '人格更新成功');
          this.dialogVisible = false;
          await this.refreshAll();
        } else {
          ElementPlus.ElMessage.error((result && result.error) || '操作失败，请重试');
        }
      } catch (e) {
        console.error('[PersonaManagement] Save persona failed:', e);
        ElementPlus.ElMessage.error('保存失败: ' + (e.message || '网络错误'));
      } finally {
        this.saving = false;
      }
    },

    /* ---------- Delete ---------- */
    deletePersona(personaId) {
      var self = this;
      ElementPlus.ElMessageBox.confirm(
        '确定要删除人格 "' + personaId + '" 吗？此操作不可撤销。',
        '删除人格',
        {
          confirmButtonText: '确认删除',
          cancelButtonText: '取消',
          type: 'warning',
        }
      ).then(async function () {
        try {
          var resp = await fetch('/api/persona_management/delete/' + encodeURIComponent(personaId), {
            method: 'POST',
          });
          var result = await resp.json();

          if (resp.ok) {
            ElementPlus.ElMessage.success('已删除人格: ' + personaId);
            await self.refreshAll();
          } else {
            ElementPlus.ElMessage.error((result && result.error) || '删除失败');
          }
        } catch (e) {
          console.error('[PersonaManagement] Delete persona failed:', e);
          ElementPlus.ElMessage.error('删除失败: ' + (e.message || '网络错误'));
        }
      }).catch(function () {
        // User cancelled, do nothing
      });
    },

    /* ---------- Export ---------- */
    async exportPersona(personaId) {
      try {
        var resp = await fetch('/api/persona_management/export/' + encodeURIComponent(personaId));
        if (!resp.ok) {
          var errData = await resp.json().catch(function () { return {}; });
          ElementPlus.ElMessage.error((errData && errData.error) || '导出失败');
          return;
        }

        var blob = await resp.blob();
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'persona_' + personaId + '.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        ElementPlus.ElMessage.success('人格已导出: ' + personaId);
      } catch (e) {
        console.error('[PersonaManagement] Export persona failed:', e);
        ElementPlus.ElMessage.error('导出失败: ' + (e.message || '网络错误'));
      }
    },

    /* ---------- Import ---------- */
    openImportDialog() {
      this.importFile = null;
      this.importDialogVisible = true;
    },

    handleImportFile(e) {
      var files = e.target.files;
      this.importFile = files && files.length > 0 ? files[0] : null;
    },

    async submitImport() {
      if (!this.importFile) {
        ElementPlus.ElMessage.error('请先选择一个文件');
        return;
      }

      this.importing = true;
      try {
        var formData = new FormData();
        formData.append('file', this.importFile);

        var resp = await fetch('/api/persona_management/import', {
          method: 'POST',
          body: formData,
        });

        var result = await resp.json();

        if (resp.ok) {
          ElementPlus.ElMessage.success('人格导入成功');
          this.importDialogVisible = false;
          await this.refreshAll();
        } else {
          ElementPlus.ElMessage.error((result && result.error) || '导入失败');
        }
      } catch (e) {
        console.error('[PersonaManagement] Import persona failed:', e);
        ElementPlus.ElMessage.error('导入失败: ' + (e.message || '网络错误'));
      } finally {
        this.importing = false;
      }
    },
  },

  async mounted() {
    var self = this;

    // Load personas and default persona in parallel
    try {
      await Promise.all([this.loadPersonas(), this.loadDefaultPersona()]);
    } catch (e) {
      console.error('[PersonaManagement] Initial load failed:', e);
    } finally {
      this.loading = false;
    }

    // Auto-refresh every 30 seconds
    this.refreshTimer = setInterval(function () {
      self.loadPersonas();
      self.loadDefaultPersona();
    }, 30000);
  },

  beforeUnmount() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  },
};
