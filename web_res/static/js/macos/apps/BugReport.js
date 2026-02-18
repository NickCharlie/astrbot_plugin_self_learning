/**
 * Bug 反馈 - Bug Report App
 * 支持表单提交 + 图片上传的 Bug 反馈工具
 */
window.AppBugReport = {
  props: { app: Object },
  template: `
    <div class="app-content">
      <!-- 加载状态 -->
      <div v-if="configLoading" class="loading-center" style="height:100%;flex-direction:column;">
        <i class="material-icons" style="font-size:36px;animation:spin 1s linear infinite;margin-bottom:12px;">refresh</i>
        <span style="font-size:13px;">加载配置中...</span>
        <style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>
      </div>

      <!-- 功能已禁用 -->
      <div v-else-if="!configEnabled" style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:30px;box-sizing:border-box;">
        <i class="material-icons" style="font-size:56px;color:#8e8e93;margin-bottom:12px;">block</i>
        <h2 style="margin:0 0 8px;font-size:20px;font-weight:600;color:#333;">Bug 反馈已关闭</h2>
        <p style="margin:0;font-size:13px;color:#86868b;text-align:center;max-width:360px;">{{ disabledMessage }}</p>
      </div>

      <!-- 主表单 -->
      <template v-else>
        <div class="section-card">
          <h3>
            <i class="material-icons" style="font-size:16px;vertical-align:text-bottom;margin-right:4px;color:#ff2d55;">bug_report</i>
            Bug 反馈
          </h3>

          <el-form ref="bugForm" :model="form" label-position="top" size="default">

            <!-- 标题 -->
            <el-form-item label="标题" required>
              <el-input
                v-model="form.bugTitle"
                placeholder="请简要描述遇到的问题"
                maxlength="200"
                show-word-limit
                clearable
              />
            </el-form-item>

            <!-- 类型 / 严重程度 / 优先级 -->
            <div style="display:flex;gap:12px;flex-wrap:wrap;">
              <el-form-item label="类型" style="flex:1;min-width:140px;">
                <el-select v-model="form.bugType" placeholder="选择类型" style="width:100%;">
                  <el-option
                    v-for="opt in typeOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="严重程度" style="flex:1;min-width:140px;">
                <el-select v-model="form.bugSeverity" placeholder="选择严重程度" style="width:100%;">
                  <el-option
                    v-for="opt in severityOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="优先级" style="flex:1;min-width:140px;">
                <el-select v-model="form.bugPriority" placeholder="选择优先级" style="width:100%;">
                  <el-option
                    v-for="opt in priorityOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </el-form-item>
            </div>

            <!-- 复现步骤 -->
            <el-form-item label="复现步骤" required>
              <el-input
                v-model="form.bugSteps"
                type="textarea"
                :rows="4"
                placeholder="1. 打开某页面&#10;2. 点击某按钮&#10;3. 观察到异常行为..."
                maxlength="2000"
                show-word-limit
              />
            </el-form-item>

            <!-- 详细描述 -->
            <el-form-item label="详细描述">
              <el-input
                v-model="form.bugDescription"
                type="textarea"
                :rows="3"
                placeholder="请详细描述问题的表现、期望行为等"
                maxlength="3000"
                show-word-limit
              />
            </el-form-item>

            <!-- 环境信息 -->
            <el-form-item label="环境信息">
              <el-input
                v-model="form.bugEnvironment"
                type="textarea"
                :rows="2"
                placeholder="操作系统、浏览器版本、Python 版本等"
                maxlength="1000"
              />
            </el-form-item>

            <!-- 联系邮箱 / 版本号 -->
            <div style="display:flex;gap:12px;flex-wrap:wrap;">
              <el-form-item label="联系邮箱" style="flex:1;min-width:200px;">
                <el-input
                  v-model="form.bugEmail"
                  placeholder="可选，方便我们回复您"
                  clearable
                />
              </el-form-item>

              <el-form-item label="版本号" style="flex:1;min-width:200px;">
                <el-input
                  v-model="form.bugBuild"
                  placeholder="插件版本号"
                  clearable
                />
              </el-form-item>
            </div>

            <!-- 包含日志 -->
            <el-form-item>
              <el-checkbox v-model="form.bugIncludeLogs">包含日志</el-checkbox>
              <div v-if="form.bugIncludeLogs && logPreview" style="margin-top:8px;padding:10px 12px;background:#f5f5f7;border-radius:8px;border:1px solid #e5e5e5;max-height:120px;overflow-y:auto;">
                <pre style="margin:0;font-size:11px;color:#555;white-space:pre-wrap;word-break:break-all;font-family:'SF Mono',Menlo,monospace;">{{ logPreview }}</pre>
              </div>
            </el-form-item>

            <!-- 图片上传 -->
            <el-form-item label="截图附件">
              <el-upload
                ref="uploadRef"
                :auto-upload="false"
                :file-list="fileList"
                :on-change="handleFileChange"
                :on-remove="handleFileRemove"
                :before-upload="beforeUpload"
                :limit="maxImages"
                :on-exceed="handleExceed"
                accept="image/*"
                list-type="picture-card"
                drag
                multiple
              >
                <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:8px;">
                  <i class="material-icons" style="font-size:28px;color:#c0c4cc;margin-bottom:4px;">cloud_upload</i>
                  <div style="font-size:11px;color:#86868b;">点击或拖拽上传</div>
                  <div style="font-size:10px;color:#c0c4cc;margin-top:2px;">最多 {{ maxImages }} 张，单张不超过 {{ formatBytes(maxImageBytes) }}</div>
                </div>
              </el-upload>
            </el-form-item>

            <!-- 提交按钮 -->
            <el-form-item>
              <el-button
                type="primary"
                @click="submitReport"
                :loading="submitting"
                :disabled="submitting"
                style="width:100%;"
              >
                <i class="material-icons" style="font-size:14px;vertical-align:text-bottom;margin-right:4px;" v-if="!submitting">send</i>
                {{ submitting ? '提交中...' : '提交反馈' }}
              </el-button>
            </el-form-item>

          </el-form>
        </div>

        <!-- 提交结果 -->
        <div v-if="submitResult" class="section-card" :style="{borderLeft: submitSuccess ? '3px solid #67c23a' : '3px solid #f56c6c'}">
          <div style="display:flex;align-items:center;gap:8px;">
            <i class="material-icons" :style="{fontSize:'20px', color: submitSuccess ? '#67c23a' : '#f56c6c'}">
              {{ submitSuccess ? 'check_circle' : 'error' }}
            </i>
            <span style="font-size:13px;font-weight:500;">{{ submitResult }}</span>
          </div>
        </div>

        <!-- 社交链接 -->
        <div class="social-links">
          <a class="qq-link" href="https://qm.qq.com/q/1021544792" target="_blank" rel="noopener">QQ群: 1021544792</a>
          <a class="gh-link" href="https://github.com/NickCharlie/astrbot_plugin_self_learning" target="_blank" rel="noopener">GitHub</a>
        </div>
      </template>
    </div>
  `,

  data() {
    return {
      // Config state
      configLoading: true,
      configEnabled: true,
      disabledMessage: "",

      // Form options from config
      typeOptions: [],
      severityOptions: [],
      priorityOptions: [],
      logPreview: "",
      maxImages: 6,
      maxImageBytes: 8 * 1024 * 1024,

      // Form data
      form: {
        bugTitle: "",
        bugType: "",
        bugSeverity: "",
        bugPriority: "",
        bugSteps: "",
        bugDescription: "",
        bugEnvironment: "",
        bugEmail: "",
        bugBuild: "",
        bugIncludeLogs: false,
      },

      // File upload
      fileList: [],

      // Submit state
      submitting: false,
      submitResult: "",
      submitSuccess: false,
    };
  },

  methods: {
    /**
     * Load bug report configuration from the server.
     */
    async loadConfig() {
      this.configLoading = true;
      try {
        const resp = await window.MacOSApi.get("/api/bug_report/config");
        if (resp && resp.data) {
          const cfg = resp.data;
          this.configEnabled = cfg.enabled !== false;
          this.disabledMessage = cfg.message || "Bug 反馈功能当前未开放。";

          // Populate select options
          this.severityOptions = cfg.severityOptions || [];
          this.priorityOptions = cfg.priorityOptions || [];
          this.typeOptions = cfg.typeOptions || [];

          // Limits
          this.maxImages = cfg.maxImages || 6;
          this.maxImageBytes = cfg.maxImageBytes || 8 * 1024 * 1024;

          // Log preview
          this.logPreview = cfg.logPreview || "";

          // Default values
          if (cfg.defaultBuild) {
            this.form.bugBuild = cfg.defaultBuild;
          }

          // Set first option as default if available
          if (this.typeOptions.length > 0 && !this.form.bugType) {
            this.form.bugType = this.typeOptions[0].value;
          }
          if (this.severityOptions.length > 0 && !this.form.bugSeverity) {
            this.form.bugSeverity = this.severityOptions[0].value;
          }
          if (this.priorityOptions.length > 0 && !this.form.bugPriority) {
            this.form.bugPriority = this.priorityOptions[0].value;
          }
        }
      } catch (e) {
        console.error("[BugReport] Failed to load config:", e);
        ElementPlus.ElMessage.error("加载 Bug 反馈配置失败");
        this.configEnabled = true; // Still allow form to show
      } finally {
        this.configLoading = false;
      }
    },

    /**
     * Validate form fields before submission.
     * Returns true if valid, false otherwise.
     */
    validateForm() {
      if (!this.form.bugTitle.trim()) {
        ElementPlus.ElMessage.warning("请填写 Bug 标题");
        return false;
      }
      if (!this.form.bugSteps.trim()) {
        ElementPlus.ElMessage.warning("请填写复现步骤");
        return false;
      }
      return true;
    },

    /**
     * Submit the bug report as multipart/form-data.
     */
    async submitReport() {
      if (!this.validateForm()) return;

      this.submitting = true;
      this.submitResult = "";
      this.submitSuccess = false;

      try {
        const fd = new FormData();

        // Append all text fields
        fd.append("bugTitle", this.form.bugTitle.trim());
        fd.append("bugType", this.form.bugType);
        fd.append("bugSeverity", this.form.bugSeverity);
        fd.append("bugPriority", this.form.bugPriority);
        fd.append("bugSteps", this.form.bugSteps.trim());
        fd.append("bugDescription", this.form.bugDescription.trim());
        fd.append("bugEnvironment", this.form.bugEnvironment.trim());
        fd.append("bugEmail", this.form.bugEmail.trim());
        fd.append("bugBuild", this.form.bugBuild.trim());
        fd.append(
          "bugIncludeLogs",
          this.form.bugIncludeLogs ? "true" : "false",
        );

        // If include logs is checked, append log preview content
        if (this.form.bugIncludeLogs && this.logPreview) {
          fd.append("logContent", this.logPreview);
        }

        // Append uploaded files
        for (const file of this.fileList) {
          if (file.raw) {
            fd.append("bugAttachments", file.raw);
          }
        }

        const resp = await window.MacOSApi.postForm("/api/bug_report", fd);

        if (resp && resp.ok) {
          this.submitSuccess = true;
          this.submitResult =
            resp.data.message || "反馈提交成功，感谢您的报告！";
          ElementPlus.ElMessage.success("Bug 反馈提交成功");
          this.resetForm();
        } else {
          const errMsg =
            (resp && resp.data && resp.data.error) || "提交失败，请稍后重试";
          this.submitSuccess = false;
          this.submitResult = errMsg;
          ElementPlus.ElMessage.error(errMsg);
        }
      } catch (e) {
        console.error("[BugReport] Submit failed:", e);
        this.submitSuccess = false;
        this.submitResult = "提交失败: " + (e.message || "网络错误");
        ElementPlus.ElMessage.error("提交失败: " + (e.message || "网络错误"));
      } finally {
        this.submitting = false;
      }
    },

    /**
     * Reset the form to initial state after successful submission.
     */
    resetForm() {
      this.form.bugTitle = "";
      this.form.bugType =
        this.typeOptions.length > 0 ? this.typeOptions[0].value : "";
      this.form.bugSeverity =
        this.severityOptions.length > 0 ? this.severityOptions[0].value : "";
      this.form.bugPriority =
        this.priorityOptions.length > 0 ? this.priorityOptions[0].value : "";
      this.form.bugSteps = "";
      this.form.bugDescription = "";
      this.form.bugEnvironment = "";
      this.form.bugEmail = "";
      this.form.bugIncludeLogs = false;
      this.fileList = [];
      // Keep bugBuild as it was (pre-filled from config)
    },

    /**
     * Handle file selection via el-upload on-change.
     * Validates file size before accepting.
     */
    handleFileChange(file, newFileList) {
      // Validate file size
      if (file.raw && file.raw.size > this.maxImageBytes) {
        ElementPlus.ElMessage.warning(
          '文件 "' +
            file.name +
            '" 超过大小限制 (' +
            this.formatBytes(this.maxImageBytes) +
            ")，已忽略",
        );
        // Remove the oversized file from the list
        const idx = newFileList.indexOf(file);
        if (idx > -1) {
          newFileList.splice(idx, 1);
        }
        this.fileList = newFileList;
        return;
      }
      this.fileList = newFileList;
    },

    /**
     * Handle file removal from the upload list.
     */
    handleFileRemove(file, newFileList) {
      this.fileList = newFileList;
    },

    /**
     * Called when file count exceeds the limit.
     */
    handleExceed(files, fileList) {
      ElementPlus.ElMessage.warning("最多上传 " + this.maxImages + " 张图片");
    },

    /**
     * Before-upload hook (returns false to prevent auto-upload).
     */
    beforeUpload(file) {
      if (file.size > this.maxImageBytes) {
        ElementPlus.ElMessage.warning(
          '文件 "' +
            file.name +
            '" 超过大小限制 (' +
            this.formatBytes(this.maxImageBytes) +
            ")",
        );
        return false;
      }
      return false; // Always prevent auto-upload
    },

    /**
     * Format bytes to human readable string.
     */
    formatBytes(bytes) {
      if (bytes === 0) return "0 B";
      const units = ["B", "KB", "MB", "GB"];
      const i = Math.floor(Math.log(bytes) / Math.log(1024));
      const val = bytes / Math.pow(1024, i);
      return (i === 0 ? val : val.toFixed(1)) + " " + units[i];
    },
  },

  mounted() {
    this.loadConfig();
  },

  beforeUnmount() {
    // cleanup if needed
  },
};
