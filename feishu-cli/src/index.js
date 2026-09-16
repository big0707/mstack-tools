/**
 * FeishuCLI - 飞书 CLI 核心 SDK
 * 供 AI Agent 以编程方式调用
 */

import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import FeishuAPI from './api.js';
import { assertCleanText } from './encoding.js';

// 自动加载 .env（支持被直接导入时使用）
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
dotenv.config({ path: join(__dirname, '../.env') });

class FeishuCLI {
  constructor(config = {}) {
    // 优先使用传入的配置，其次环境变量
    this.appId = config.appId || process.env.FEISHU_APP_ID;
    this.appSecret = config.appSecret || process.env.FEISHU_APP_SECRET;
    this.defaultFolderToken = config.folderToken || process.env.FEISHU_DEFAULT_FOLDER_TOKEN;
    this.defaultShareMode = config.shareMode || process.env.FEISHU_DEFAULT_SHARE_MODE || 'internal';
    this.defaultLinkPermission = config.linkPermission || process.env.FEISHU_INTERNAL_LINK_PERMISSION || 'tenant_readable';
    this.defaultMemberPermission = config.memberPermission || process.env.FEISHU_DEFAULT_MEMBER_PERMISSION || 'view';
    this.defaultMemberIds = this._parseCsv(config.memberIds || process.env.FEISHU_DEFAULT_MEMBER_IDS);

    if (!this.appId || !this.appSecret) {
      throw new Error('缺少飞书应用凭证: appId 和 appSecret 必填');
    }

    this.api = new FeishuAPI({
      appId: this.appId,
      appSecret: this.appSecret
    });
  }

  _parseCsv(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value.map(String).map(s => s.trim()).filter(Boolean);
    return String(value).split(',').map(s => s.trim()).filter(Boolean);
  }

  /**
   * 创建文档
   * @param {Object} options
   * @param {string} options.title - 文档标题
   * @param {string} options.content - 文档内容 (支持纯文本或 markdown)
   * @param {string} options.folderToken - 目标文件夹 (可选)
   * @returns {Promise<Object>} { documentToken, url, title }
   */
  async createDocument({ title, content, folderToken, tables, force = false }) {
    // 0. 乱码防线：出现 ?? / U+FFFD 说明源内容编码已损坏，直接拒绝写入
    assertCleanText(title, '文档标题', force);
    assertCleanText(content, '文档内容', force);
    if (Array.isArray(tables)) {
      for (const t of tables) assertCleanText(JSON.stringify(t), '文档表格数据', force);
    }

    // 1. 创建空文档
    const doc = await this.api.createDocument(
      title,
      folderToken || this.defaultFolderToken
    );

    const documentId = doc.document?.document_id || doc.document_id;

    if (!documentId) {
      throw new Error('创建文档失败: 未返回 document_id');
    }

    // 2. 写入内容 (将纯文本转为 docx 内容块)
    if (content) {
      const blocks = this._textToBlocks(content);
      await this.api.appendDocumentBlocks(documentId, blocks);
    }

    // 追加真实表格（绕开 markdown 表格渲染不可靠的问题）
    if (Array.isArray(tables)) {
      for (const t of tables) {
        await this.api.createDocxTable(documentId, t);
      }
    }

    // 3. 构造返回结果
    return {
      success: true,
      data: {
        documentToken: documentId,
        url: `https://www.feishu.cn/docx/${documentId}`,
        title: title || '未命名文档'
      }
    };
  }

  /**
   * 发送通知给用户
   * @param {Object} options
   * @param {string} options.userId - 用户 open_id
   * @param {string} options.message - 消息内容
   * @param {string} options.msgType - 消息类型: text, card
   * @returns {Promise<Object>}
   */
  async notifyUser({ userId, chatId, message, msgType = 'text', at = null }) {
    const receiveId = chatId || userId;
    const receiveIdType = chatId ? 'chat_id' : 'open_id';
    if (!receiveId) {
      throw new Error('缺少 userId 或 chatId');
    }

    // 群文本消息支持 @：在文本前插入 <at> 标签（at 值为 open_id 或 "all"）
    let text = message;
    if (at && msgType !== 'card') {
      const ats = String(at).split(',').map(s => s.trim()).filter(Boolean);
      const atTags = ats
        .map(a => (a === 'all' ? '<at user_id="all">所有人</at>' : `<at user_id="${a}"></at>`))
        .join(' ');
      text = `${atTags} ${message}`;
    }

    let result;

    if (msgType === 'card') {
      // 发送卡片消息 (更美观)
      result = await this.api.sendCardMessage(receiveId, message, receiveIdType);
    } else {
      result = await this.api.sendMessage(receiveId, text, 'text', receiveIdType);
    }

    return {
      success: true,
      data: {
        messageId: result?.message_id,
        receiveId,
        receiveIdType
      }
    };
  }

  /**
   * 创建文档并通知用户 (组合操作)
   * @param {Object} options
   * @param {string} options.title - 文档标题
   * @param {string} options.content - 文档内容
   * @param {string} options.userId - 要通知的用户 open_id
   * @param {string} options.notifyMessage - 自定义通知消息 (可选)
   */
  async createAndNotify({ title, content, userId, notifyMessage, folderToken, sharePermission, makePublic = false, makeInternal = false, makePrivate = false, linkPermission, memberIds, tables, force = false }) {
    // 1. 创建文档
    const docResult = await this.createDocument({ title, content, folderToken, tables, force });
    const docToken = docResult.data.documentToken;

    // 2. 授权：云文档默认归 bot 所有，被通知用户打不开，必须加权限
    //    （LearyClaw 踩坑：子代理/通知流程最常漏这一步）
    const warnings = [];
    if (makePublic) {
      try { await this.api.setDocPublic(docToken); }
      catch (e) { warnings.push(`设公开失败: ${e.message}`); }
    } else if (makePrivate || this.defaultShareMode === 'private') {
      try { await this.api.setDocPrivate(docToken, 'docx'); }
      catch (e) { warnings.push(`设机密权限失败: ${e.message}`); }
    } else if (!makePrivate && (makeInternal || this.defaultShareMode === 'internal')) {
      try { await this.api.setDocInternal(docToken, 'docx', linkPermission || this.defaultLinkPermission); }
      catch (e) { warnings.push(`设企业内部分享失败: ${e.message}`); }
    }

    const grantMemberIds = [...new Set([
      ...this.defaultMemberIds,
      ...this._parseCsv(memberIds),
      ...(userId ? [userId] : [])
    ])];
    const memberPermission = sharePermission || this.defaultMemberPermission;
    for (const memberId of grantMemberIds) {
      try { await this.api.addDocMember(docToken, memberId, memberPermission); }
      catch (e) { warnings.push(`为用户 ${memberId} 加权限失败: ${e.message}`); }
    }
    if (warnings.length) docResult.data.permissionWarnings = warnings;

    // 3. 发送通知
    if (userId) {
      const message = notifyMessage || `文档「${title}」已创建，点击查看: ${docResult.data.url}`;
      await this.notifyUser({ userId, message });
    }

    return docResult;
  }

  /**
   * 查询用户信息 (通过邮箱或手机号)
   * @param {Object} options
   * @param {string} options.email - 邮箱
   * @param {string} options.mobile - 手机号
   */
  async getUserId({ email, mobile }) {
    const userId = await this.api.getUserId({ email, mobile });
    if (!userId) {
      return {
        success: false,
        error: '未找到匹配用户：open_id 为空。请检查邮箱/手机号是否正确，或应用是否拥有 contact 通讯录权限',
        data: {}
      };
    }
    return { success: true, data: { userId } };
  }

  /**
   * 构建文档创建卡片 (用于通知) —— 飞书卡片 Schema 2.0
   * V2 必须用 body.elements；V2 已移除 tag:action 容器，
   * 按钮改为 tag:"button" 直接作为 body 元素（表格在 V2 下才能渲染）。
   * @param {Object} docInfo
   */
  buildDocCard({ title, url, description = '' }) {
    const md = [`**${title}**`];
    if (description) md.push(description);

    const elements = [{ tag: 'markdown', content: md.join('\n') }];
    if (url) {
      elements.push({
        tag: 'button',
        text: { tag: 'plain_text', content: '查看文档' },
        type: 'primary',
        url
      });
    }

    return {
      schema: '2.0',
      config: { wide_screen_mode: true },
      header: {
        title: { tag: 'plain_text', content: '新文档通知' },
        template: 'blue'
      },
      body: { elements }
    };
  }

  /**
   * 将 markdown 文本转换为飞书 docx 内容块
   * 支持：# 标题、-/* 无序列表、1. 有序列表、```代码块```、**粗体**
   * @private
   */
  _textToBlocks(text) {
    // 归一化换行（CRLF / CR -> LF），避免 Windows 换行把 \r 带进内容
    const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const blocks = [];
    let i = 0;

    // 飞书 docx 每种块类型用各自的字段名承载 elements（仅 text 用 text）
    const fieldOf = (t) => ({
      2: 'text', 3: 'heading1', 4: 'heading2', 5: 'heading3',
      6: 'heading4', 7: 'heading5', 8: 'heading6',
      12: 'bullet', 13: 'ordered'
    })[t];

    while (i < lines.length) {
      const trimmed = lines[i].trim();

      // 空行跳过
      if (!trimmed) { i++; continue; }

      // 代码块 ```lang ... ```
      if (trimmed.startsWith('```')) {
        const codeLines = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith('```')) {
          codeLines.push(lines[i]);
          i++;
        }
        i++; // 跳过结束 ```
        blocks.push({
          block_type: 14,
          code: {
            elements: [{ text_run: { content: codeLines.join('\n') } }],
            style: { language: 1 } // 1 = PlainText
          }
        });
        continue;
      }

      // 标题 / 列表 / 普通段落（注意长前缀优先匹配）
      let blockType = 2;
      let content = trimmed;
      if (content.startsWith('###### ')) { blockType = 8; content = content.slice(7); }
      else if (content.startsWith('##### ')) { blockType = 7; content = content.slice(6); }
      else if (content.startsWith('#### ')) { blockType = 6; content = content.slice(5); }
      else if (content.startsWith('### ')) { blockType = 5; content = content.slice(4); }
      else if (content.startsWith('## ')) { blockType = 4; content = content.slice(3); }
      else if (content.startsWith('# ')) { blockType = 3; content = content.slice(2); }
      else if (/^[-*]\s+/.test(content)) { blockType = 12; content = content.replace(/^[-*]\s+/, ''); }
      else if (/^\d+\.\s+/.test(content)) { blockType = 13; content = content.replace(/^\d+\.\s+/, ''); }

      blocks.push({
        block_type: blockType,
        [fieldOf(blockType)]: { elements: this._parseInline(content) }
      });
      i++;
    }

    return blocks;
  }

  /**
   * 解析行内 **粗体**，拆成多个 text_run
   * @private
   */
  _parseInline(text) {
    const elements = [];
    const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(s => s !== '');
    for (const part of parts) {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        elements.push({
          text_run: { content: part.slice(2, -2), text_element_style: { bold: true } }
        });
      } else if (part) {
        elements.push({ text_run: { content: part } });
      }
    }
    return elements.length ? elements : [{ text_run: { content: '' } }];
  }

  /**
   * 创建电子表格并写入二维数据（用于数据分析结果落表 / 数据导出）
   * @param {Object} options
   * @param {string} options.title - 表格标题
   * @param {Array<Array>} options.data - 二维数据，第一行可为表头
   * @param {string} options.folderToken - 目标文件夹 (可选)
   * @returns {Promise<Object>} { spreadsheetToken, sheetId, url, title }
   */
  async createSheet({ title, data, folderToken, force = false }) {
    assertCleanText(title, '表格标题', force);
    if (Array.isArray(data)) assertCleanText(JSON.stringify(data), '表格数据', force);

    const { spreadsheetToken, url } = await this.api.createSpreadsheet(
      title, folderToken || this.defaultFolderToken
    );
    if (!spreadsheetToken) {
      throw new Error('创建表格失败: 未返回 spreadsheet_token');
    }

    const sheets = await this.api.getSheets(spreadsheetToken);
    const sheetId = sheets[0]?.sheet_id;
    if (!sheetId) {
      throw new Error('创建表格失败: 未取到工作表 sheet_id');
    }

    if (data && data.length) {
      await this.api.writeSheetValues(spreadsheetToken, sheetId, data);
    }

    return {
      success: true,
      data: { spreadsheetToken, sheetId, url, title: title || '未命名表格' }
    };
  }

  /**
   * 向现有电子表格追加数据。底层使用 values_append + INSERT_ROWS，
   * 因此不会从 A1 重写已有内容。
   */
  async appendSheet({ spreadsheetToken, sheetId, data, force = false }) {
    if (Array.isArray(data)) {
      assertCleanText(JSON.stringify(data), '追加表格数据', force);
    }

    const result = await this.api.appendSheetValues(spreadsheetToken, sheetId, data);
    const columns = Math.max(...data.map(row => row.length));

    return {
      success: true,
      data: {
        spreadsheetToken,
        sheetId,
        appendedRows: data.length,
        appendedColumns: columns,
        tableRange: result?.tableRange,
        updates: result?.updates,
        revision: result?.revision
      }
    };
  }

  /**
   * 创建表格 + 授权 + 通知（组合操作，权限 type=sheet）
   */
  async createSheetAndNotify({ title, data, folderToken, userId, notifyMessage, makePublic = false, makeInternal = false, makePrivate = false, linkPermission, memberIds, sharePermission, force = false }) {
    const result = await this.createSheet({ title, data, folderToken, force });
    const token = result.data.spreadsheetToken;

    const warnings = [];
    if (makePublic) {
      try { await this.api.setDocPublic(token, 'sheet'); }
      catch (e) { warnings.push(`设公开失败: ${e.message}`); }
    } else if (makePrivate || this.defaultShareMode === 'private') {
      try { await this.api.setDocPrivate(token, 'sheet'); }
      catch (e) { warnings.push(`设机密权限失败: ${e.message}`); }
    } else if (!makePrivate && (makeInternal || this.defaultShareMode === 'internal')) {
      try { await this.api.setDocInternal(token, 'sheet', linkPermission || this.defaultLinkPermission); }
      catch (e) { warnings.push(`设企业内部分享失败: ${e.message}`); }
    }

    const grantMemberIds = [...new Set([
      ...this.defaultMemberIds,
      ...this._parseCsv(memberIds),
      ...(userId ? [userId] : [])
    ])];
    const memberPermission = sharePermission || this.defaultMemberPermission;
    for (const memberId of grantMemberIds) {
      try { await this.api.addDocMember(token, memberId, memberPermission, 'sheet'); }
      catch (e) { warnings.push(`为用户 ${memberId} 加权限失败: ${e.message}`); }
    }
    if (warnings.length) result.data.permissionWarnings = warnings;

    if (userId) {
      const message = notifyMessage || `表格「${title}」已创建，点击查看: ${result.data.url}`;
      await this.notifyUser({ userId, message });
    }

    return result;
  }
}

export default FeishuCLI;
