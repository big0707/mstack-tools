/**
 * 飞书 API 底层封装
 * 处理认证、请求、错误处理
 */

const FEISHU_API_BASE = 'https://open.feishu.cn/open-apis';
const DEFAULT_TIMEOUT_MS = 30000;   // 业务接口默认超时
const TOKEN_TIMEOUT_MS = 10000;     // 获取 token 超时
const MAX_RETRIES = 1;              // 网络/5xx 自动重试次数

class FeishuAPI {
  constructor({ appId, appSecret }) {
    this.appId = appId;
    this.appSecret = appSecret;
    this.accessToken = null;
    this.tokenExpireAt = 0;
  }

  /**
   * 获取 tenant_access_token（应用身份权限模式）
   */
  async getAccessToken() {
    // Token 未过期直接返回
    if (this.accessToken && Date.now() < this.tokenExpireAt) {
      return this.accessToken;
    }

    const { data } = await this._fetchJson(
      `${FEISHU_API_BASE}/auth/v3/tenant_access_token/internal`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          app_id: this.appId,
          app_secret: this.appSecret
        })
      },
      TOKEN_TIMEOUT_MS
    );

    if (data.code !== 0) {
      throw new Error(`获取 access_token 失败: ${data.msg} (code: ${data.code})`);
    }

    this.accessToken = data.tenant_access_token;
    // 提前 5 分钟过期，避免边界问题；expire 缺失时兜底 7200s 防 NaN
    const expire = data.expire || 7200;
    this.tokenExpireAt = Date.now() + (expire - 300) * 1000;

    return this.accessToken;
  }

  /**
   * 发送 API 请求
   * - 超时控制 (AbortController)，避免连接 stall 时永久挂起（卡死根因）
   * - 网络/5xx/429 自动重试 1 次
   * - token 失效自动刷新后重试 1 次
   */
  async request(path, options = {}, requestOptions = {}) {
    const url = path.startsWith('http') ? path : `${FEISHU_API_BASE}${path}`;
    const {
      networkRetries = MAX_RETRIES,
      uncertainWrite = false
    } = requestOptions;

    for (let attempt = 0; attempt <= 1; attempt++) {
      const token = await this.getAccessToken();
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers
      };
      const { status, data } = await this._fetchJson(
        url,
        { ...options, headers },
        DEFAULT_TIMEOUT_MS,
        { networkRetries, uncertainWrite }
      );

      if (data.code === 0) {
        return data.data;
      }

      // token 失效 (99991663 过期 / 99991661 非法 / HTTP 401)：刷新后重试一次
      const tokenInvalid = status === 401 || data.code === 99991663 || data.code === 99991661;
      if (tokenInvalid && attempt === 0) {
        this.tokenExpireAt = 0; // 强制下次重新获取 token
        continue;
      }

      throw new Error(`API 请求失败: ${data.msg} (code: ${data.code})`);
    }
  }

  /**
   * 带超时与重试的 fetch 封装，统一返回 { status, data }
   * @private
   */
  async _fetchJson(url, options, timeoutMs, requestOptions = {}) {
    const {
      networkRetries = MAX_RETRIES,
      uncertainWrite = false
    } = requestOptions;
    let lastErr;
    for (let attempt = 0; attempt <= networkRetries; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        const text = await res.text();

        let data;
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          throw new Error(`飞书返回非 JSON 响应 (HTTP ${res.status}): ${text.slice(0, 200)}`);
        }

        // 5xx / 429 视为可重试
        if ((res.status >= 500 || res.status === 429) && attempt < networkRetries) {
          lastErr = new Error(`飞书服务暂不可用 (HTTP ${res.status})`);
          continue;
        }
        if ((res.status >= 500 || res.status === 429) && uncertainWrite) {
          throw new Error(
            `追加请求结果不确定 (HTTP ${res.status})：服务端可能已经写入。` +
            '不要直接重试；请先用 read-sheet 按记录 ID 检查是否已存在。'
          );
        }

        return { status: res.status, data };
      } catch (err) {
        // AbortError = 超时；TypeError/'fetch failed' = 网络层失败
        const isAbort = err.name === 'AbortError'
          || (err.cause && err.cause.name === 'AbortError')
          || /aborted/i.test(err.message);
        const isNetwork = err.name === 'TypeError' || /fetch failed/i.test(err.message);

        // 仅网络层失败重试；超时不重试（避免对 stall 连接翻倍等待）
        if (isNetwork && attempt < networkRetries) {
          lastErr = err;
          continue;
        }
        if (uncertainWrite && (isNetwork || isAbort)) {
          throw new Error(
            '追加请求结果不确定：连接中断或超时，服务端可能已经写入。' +
            '不要直接重试；请先用 read-sheet 按记录 ID 检查是否已存在。'
          );
        }
        if (isAbort) {
          throw new Error(`请求超时 (${timeoutMs}ms): ${url}`);
        }
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }
    throw lastErr || new Error(`请求失败: ${url}`);
  }

  /**
   * 创建文档 (docx)
   * @param {string} title - 文档标题
   * @param {string} folderToken - 父文件夹 token (可选)
   */
  async createDocument(title, folderToken) {
    const body = { title };
    if (folderToken && folderToken.trim() !== '') {
      body.folder_token = folderToken;
    }

    return this.request('/docx/v1/documents', {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  /**
   * 向文档追加内容块
   * @param {string} documentId - 文档 ID
   * @param {Array} blocks - 内容块数组
   */
  async appendDocumentBlocks(documentId, blocks) {
    // 飞书 docx 单次最多创建 50 个 children，长报告需要分批追加
    const BATCH = 50;
    let last;
    for (let i = 0; i < blocks.length; i += BATCH) {
      // 不传 index：飞书 docx 默认追加到文档末尾。-1 非文档取值，可能被当 0 前置插入
      last = await this.request(`/docx/v1/documents/${documentId}/blocks/${documentId}/children`, {
        method: 'POST',
        body: JSON.stringify({ children: blocks.slice(i, i + BATCH) })
      });
    }
    return last;
  }

  /**
   * 发送单聊消息
   * @param {string} userId - 用户 open_id
   * @param {string} message - 消息内容
   * @param {string} msgType - 消息类型: text, interactive, post
   */
  async sendMessage(receiveId, message, msgType = 'text', receiveIdType = 'open_id') {
    // text: content 为 {text}; 其他类型 (interactive/post 等): content 为消息体 JSON
    const content = msgType === 'text'
      ? JSON.stringify({ text: message })
      : JSON.stringify(message);

    return this.request(`/im/v1/messages?receive_id_type=${receiveIdType}`, {
      method: 'POST',
      body: JSON.stringify({
        receive_id: receiveId,
        msg_type: msgType,
        content
      })
    });
  }

  /**
   * 发送卡片消息 (带按钮、链接等)
   * @param {string} userId - 用户 open_id
   * @param {Object} card - 卡片配置
   */
  async sendCardMessage(receiveId, card, receiveIdType = 'open_id') {
    return this.sendMessage(receiveId, card, 'interactive', receiveIdType);
  }

  /** 列出机器人所在的群 [{ chat_id, name, owner_id, ... }] */
  async listChats() {
    const data = await this.request('/im/v1/chats?user_id_type=open_id&page_size=100', {
      method: 'GET'
    });
    return data?.items || [];
  }

  /**
   * 根据邮箱或手机号获取用户 open_id
   * @param {string} email - 邮箱
   * @param {string} mobile - 手机号
   */
  async getUserId({ email, mobile }) {
    const params = new URLSearchParams();
    if (email) {
      params.append('user_id_type', 'open_id');
      params.append('emails', email);
    }
    if (mobile) {
      params.append('user_id_type', 'open_id');
      params.append('mobiles', mobile);
    }

    let data;
    try {
      data = await this.request(`/contact/v3/users/batch_get_id?${params.toString()}`, {
        method: 'GET'
      });
    } catch (e) {
      // 用户不存在时飞书返回 99992351，归一为 null（交由上层给出友好提示）
      if (/99992351/.test(e.message)) return null;
      throw e;
    }

    const item = data?.user_list?.[0];
    // user_id 在 user_id_type=open_id 时即 open_id；部分版本返回 open_id 字段，兜底取
    return item?.user_id || item?.open_id || null;
  }

  /**
   * 给云文档添加成员权限
   * @param {string} docToken - 文档 token
   * @param {string} memberId - 成员 id（open_id）
   * @param {string} perm - view / edit / full_access
   */
  async addDocMember(docToken, memberId, perm = 'full_access', type = 'docx') {
    return this.request(`/drive/v1/permissions/${docToken}/members?type=${type}`, {
      method: 'POST',
      body: JSON.stringify({ member_type: 'openid', member_id: memberId, perm })
    });
  }

  /**
   * 将云文档设为「链接可编辑」（互联网获链接者可编辑）
   * 文档默认归 bot 所有，不设权限则被通知用户打不开
   */
  async setDocPublic(docToken, type = 'docx') {
    return this.request(`/drive/v1/permissions/${docToken}/public?type=${type}`, {
      method: 'PATCH',
      body: JSON.stringify({
        external_access_entity: 'open',
        security_entity: 'anyone_can_view',
        comment_entity: 'anyone_can_view',
        share_entity: 'anyone',
        link_share_entity: 'anyone_editable'
      })
    });
  }

  /**
   * 将云文档设为企业内部链接可访问，避免飞书显示“外部”。
   * linkShareEntity:
   * - tenant_readable：组织内拿到链接的人可阅读
   * - tenant_editable：组织内拿到链接的人可编辑
   */
  async setDocInternal(docToken, type = 'docx', linkShareEntity = 'tenant_readable') {
    return this.request(`/drive/v1/permissions/${docToken}/public?type=${type}`, {
      method: 'PATCH',
      body: JSON.stringify({
        external_access: false,
        external_access_entity: 'closed',
        security_entity: 'anyone_can_view',
        comment_entity: 'anyone_can_view',
        share_entity: 'same_tenant',
        link_share_entity: linkShareEntity,
        invite_external: false
      })
    });
  }

  /**
   * 将云文档设为仅授权成员可访问。
   */
  async setDocPrivate(docToken, type = 'docx') {
    return this.request(`/drive/v1/permissions/${docToken}/public?type=${type}`, {
      method: 'PATCH',
      body: JSON.stringify({
        external_access: false,
        external_access_entity: 'closed',
        security_entity: 'only_full_access',
        comment_entity: 'anyone_can_view',
        share_entity: 'same_tenant',
        link_share_entity: 'closed',
        invite_external: false
      })
    });
  }

  // ---------- 电子表格 (Sheets) ----------

  /** 创建电子表格，返回 { spreadsheetToken, url } */
  async createSpreadsheet(title, folderToken) {
    const body = { title };
    if (folderToken && folderToken.trim()) body.folder_token = folderToken;
    const data = await this.request('/sheets/v3/spreadsheets', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    const sp = data?.spreadsheet || data;
    return {
      spreadsheetToken: sp?.spreadsheet_token,
      url: sp?.url || `https://www.feishu.cn/sheets/${sp?.spreadsheet_token}`
    };
  }

  /** 获取工作表列表 [{ sheet_id, title, index }] */
  async getSheets(spreadsheetToken) {
    const data = await this.request(
      `/sheets/v3/spreadsheets/${spreadsheetToken}/sheets/query`,
      { method: 'GET' }
    );
    return data?.sheets || [];
  }

  /** 向工作表写入二维数据（自动按数据尺寸算 range，必须带结束列） */
  async writeSheetValues(spreadsheetToken, sheetId, values) {
    const rows = values.length;
    const cols = Math.max(...values.map(r => Array.isArray(r) ? r.length : 0));
    const range = `${sheetId}!A1:${this._colLetter(cols)}${rows}`;
    return this.request(`/sheets/v2/spreadsheets/${spreadsheetToken}/values`, {
      method: 'PUT',
      body: JSON.stringify({ valueRange: { range, values } })
    });
  }

  /**
   * 在现有工作表数据末尾追加二维数据，不覆盖已有非空数据。
   * 使用官方 Sheets v2 values_append 接口，并显式指定 INSERT_ROWS。
   */
  async appendSheetValues(spreadsheetToken, sheetId, values) {
    const token = typeof spreadsheetToken === 'string' ? spreadsheetToken.trim() : '';
    const sheet = typeof sheetId === 'string' ? sheetId.trim() : '';

    if (!token) throw new Error('电子表格 token 不能为空');
    if (!sheet) throw new Error('工作表 sheet_id 不能为空');
    if (!/^[A-Za-z0-9_-]+$/.test(sheet)) {
      throw new Error('工作表 sheet_id 格式无效');
    }
    if (!Array.isArray(values) || values.length === 0) {
      throw new Error('追加数据必须是非空二维数组');
    }
    if (values.length > 5000) {
      throw new Error('单次最多追加 5000 行');
    }

    for (let rowIndex = 0; rowIndex < values.length; rowIndex++) {
      const row = values[rowIndex];
      if (!Array.isArray(row) || row.length === 0) {
        throw new Error(`追加数据第 ${rowIndex + 1} 行必须是非空数组`);
      }
      if (row.length > 100) {
        throw new Error(`追加数据第 ${rowIndex + 1} 行超过 100 列`);
      }
      for (let colIndex = 0; colIndex < row.length; colIndex++) {
        const value = row[colIndex];
        if (typeof value === 'string' && value.length > 50000) {
          throw new Error(`追加数据第 ${rowIndex + 1} 行第 ${colIndex + 1} 列超过 50000 字符`);
        }
        if (typeof value === 'number' && !Number.isFinite(value)) {
          throw new Error(`追加数据第 ${rowIndex + 1} 行第 ${colIndex + 1} 列不是有限数字`);
        }
        if (typeof value === 'undefined' || typeof value === 'bigint' || typeof value === 'function') {
          throw new Error(`追加数据第 ${rowIndex + 1} 行第 ${colIndex + 1} 列不是有效 JSON 值`);
        }
      }
    }

    // 只传 sheet_id 表示工作表当前非空的最大范围，让 values_append 在整张表的
    // 最后一行之后追加；若把 range 限死为 A1:C2，长表可能会在中间插入新行。
    const range = sheet;
    let body;
    try {
      body = JSON.stringify({ valueRange: { range, values } });
    } catch (error) {
      throw new Error(`追加数据无法序列化为 JSON: ${error.message}`);
    }

    return this.request(
      `/sheets/v2/spreadsheets/${encodeURIComponent(token)}/values_append?insertDataOption=INSERT_ROWS`,
      { method: 'POST', body },
      // 非幂等追加：响应丢失时自动重试会生成重复行，因此禁用网络/5xx/429 重试。
      // 明确的 token-invalid 响应仍由 request() 刷新 token 后重试，因为该请求已被拒绝。
      { networkRetries: 0, uncertainWrite: true }
    );
  }

  /** 读取工作表数据，range 形如 "SheetId!A1:Z100" */
  async readSheetValues(spreadsheetToken, range) {
    const data = await this.request(
      `/sheets/v2/spreadsheets/${spreadsheetToken}/values/${encodeURIComponent(range)}`,
      { method: 'GET' }
    );
    return data?.valueRange?.values || [];
  }

  // ---------- docx 表格 ----------

  /**
   * 在文档末尾创建带内容的表格（一次建好，绕开 markdown 表格不可靠的问题）
   * @param {string} documentId - 文档 id
   * @param {Array<Array>} data - 二维数组，第一行可为表头
   */
  async createDocxTable(documentId, data) {
    const rows = data.length;
    const cols = Math.max(...data.map(r => Array.isArray(r) ? r.length : 0));
    const prefix = `tbl_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const cellIds = [], txtIds = [];
    for (let i = 0; i < rows * cols; i++) {
      cellIds.push(`${prefix}_cell_${i}`);
      txtIds.push(`${prefix}_txt_${i}`);
    }

    const descendants = [{
      block_id: prefix,
      block_type: 31,
      table: { property: { row_size: rows, column_size: cols } },
      children: cellIds
    }];

    for (let i = 0; i < rows * cols; i++) {
      const r = Math.floor(i / cols);
      const c = i % cols;
      const val = String(data[r]?.[c] ?? '');
      descendants.push({
        block_id: cellIds[i],
        block_type: 32,
        table_cell: {},
        children: [txtIds[i]]
      });
      descendants.push({
        block_id: txtIds[i],
        block_type: 2,
        text: { elements: [{ text_run: { content: val } }] },
        children: []
      });
    }

    return this.request(
      `/docx/v1/documents/${documentId}/blocks/${documentId}/descendant?document_revision_id=-1`,
      { method: 'POST', body: JSON.stringify({ children_id: [prefix], descendants }) }
    );
  }

  /** 列号转字母：1->A, 26->Z, 27->AA  @private */
  _colLetter(n) {
    let s = '';
    while (n > 0) {
      const m = (n - 1) % 26;
      s = String.fromCharCode(65 + m) + s;
      n = Math.floor((n - 1) / 26);
    }
    return s;
  }
}

export default FeishuAPI;
