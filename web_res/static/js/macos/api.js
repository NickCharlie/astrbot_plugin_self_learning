/**
 * API 请求封装 - 使用 fetch
 */
window.MacOSApi = {
  /**
   * 通用请求方法
   */
  async request(url, options = {}) {
    const defaultOptions = {
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
    };
    const merged = { ...defaultOptions, ...options };
    if (options.headers) {
      merged.headers = { ...defaultOptions.headers, ...options.headers };
    }
    try {
      const response = await fetch(url, merged);
      if (response.status === 401) {
        window.location.href = '/api/login';
        return null;
      }
      if (response.status === 429) {
        const data = await response.json().catch(() => ({}));
        throw { status: 429, data };
      }
      const data = await response.json();
      return { status: response.status, ok: response.ok, data };
    } catch (error) {
      if (error.status === 429) throw error;
      console.error('API request failed:', url, error);
      throw error;
    }
  },

  async get(url) {
    return this.request(url, { method: 'GET' });
  },

  async post(url, body) {
    return this.request(url, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  async postForm(url, formData) {
    return this.request(url, {
      method: 'POST',
      headers: {},
      body: formData,
    });
  },

  async del(url) {
    return this.request(url, { method: 'DELETE' });
  },

  /**
   * 检查认证状态
   */
  async checkAuth() {
    try {
      const resp = await fetch('/api/config', { credentials: 'same-origin' });
      return resp.status !== 401;
    } catch {
      return false;
    }
  }
};
