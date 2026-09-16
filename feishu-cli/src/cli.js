#!/usr/bin/env node
/**
 * 飞书 CLI 命令行入口
 * 供其他 AI Agent 或脚本调用
 */

import { Command } from 'commander';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { basename } from 'path';
import FeishuCLI from './index.js';
import { readTextFileSmart, assertCleanText } from './encoding.js';

// 获取当前文件目录，确保 .env 能正确加载
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
dotenv.config({ path: join(__dirname, '../.env') });

const program = new Command();

program
  .name('feishu-cli')
  .description('飞书 CLI - 创建文档并通知用户')
  .version('1.0.0');

// 统一输出 JSON 格式，方便 AI Agent 解析
function outputJson(data, exitCode = 0) {
  console.log(JSON.stringify(data, null, 2));
  process.exit(exitCode);
}

function handleError(error) {
  outputJson({
    success: false,
    error: error.message || String(error)
  }, 1);
}

// 从环境变量或命令行参数构建配置
function buildConfig(cmdOpts) {
  return {
    appId: cmdOpts.appId || process.env.FEISHU_APP_ID,
    appSecret: cmdOpts.appSecret || process.env.FEISHU_APP_SECRET,
    folderToken: cmdOpts.folderToken || process.env.FEISHU_DEFAULT_FOLDER_TOKEN,
    shareMode: cmdOpts.shareMode || process.env.FEISHU_DEFAULT_SHARE_MODE,
    linkPermission: cmdOpts.linkPermission || process.env.FEISHU_INTERNAL_LINK_PERMISSION,
    memberIds: cmdOpts.memberIds || process.env.FEISHU_DEFAULT_MEMBER_IDS,
    memberPermission: cmdOpts.sharePerm || process.env.FEISHU_DEFAULT_MEMBER_PERMISSION
  };
}

// 读取文本文件：自动识别编码（UTF-8/UTF-16/GBK）并去 BOM，
// 避免 Windows 上错误编码的文件把中文读成乱码后写进飞书
function readTextFile(filePath) {
  return readTextFileSmart(filePath);
}

// 从内联 JSON 或文件读取二维数组（用于表格/Sheet 数据）
function read2DArray(inline, filePath) {
  if (filePath) {
    return JSON.parse(readTextFile(filePath));
  }
  if (inline) {
    return JSON.parse(inline);
  }
  return null;
}

// append-sheet 必须且只能提供一种数据来源，避免文件与内联参数冲突。
function readAppendData(inline, filePath) {
  if (inline && filePath) {
    throw new Error('--data 与 --data-file 只能提供一个');
  }
  if (!inline && !filePath) {
    throw new Error('请提供 --data 或 --data-file');
  }
  try {
    return read2DArray(inline, filePath);
  } catch (error) {
    throw new Error(`无法解析追加数据 JSON: ${error.message}`);
  }
}

// ---------- send 命令：兼容项目旧 wrapper ----------
program
  .command('send')
  .description('发送文件内容到群；可选先创建飞书文档再发链接，兼容 send-file.ps1')
  .requiredOption('--chat-id <chatId>', '群 chat_id')
  .option('--file <path>', '要发送的 Markdown/文本文件')
  .option('-m, --message <message>', '直接发送文本；提供 --file 时优先读取文件')
  .option('--title <title>', '作为文档发送时的标题，默认取文件名')
  .option('--as-doc', '先创建飞书文档，再把链接发到群', false)
  .option('--public', '作为文档发送时设为外部链接可编辑', false)
  .option('--internal', '作为文档发送时设为企业内部链接可访问（默认）', false)
  .option('--private', '作为机密文档，仅应用创建者和授权成员可访问', false)
  .option('--link-perm <perm>', '企业内部链接权限: tenant_readable/tenant_editable')
  .option('--member-ids <ids>', '额外授权成员 open_id，逗号分隔；默认读 FEISHU_DEFAULT_MEMBER_IDS')
  .option('--share-perm <perm>', '给成员授权的权限: view/edit/full_access', process.env.FEISHU_DEFAULT_MEMBER_PERMISSION || 'view')
  .option('-f, --folder-token <token>', '作为文档发送时的目标文件夹 Token')
  .option('--force', '跳过乱码检测（默认发现 ?? / U+FFFD 会拒发）', false)
  .option('--app-id <id>', '飞书 App ID')
  .option('--app-secret <secret>', '飞书 App Secret')
  .action(async (options) => {
    try {
      if (!options.file && !options.message) {
        throw new Error('请提供 --file 或 --message');
      }
      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);
      const text = options.file ? readTextFile(options.file) : options.message;
      assertCleanText(text, options.file ? `文件 ${options.file} 内容` : '消息内容', options.force);

      if (options.asDoc) {
        const title = options.title || (options.file ? basename(options.file) : '飞书消息');
        const docResult = await feishu.createAndNotify({
          title,
          content: text,
          folderToken: options.folderToken,
          makePublic: options.public,
          makeInternal: options.internal,
          makePrivate: options.private,
          linkPermission: options.linkPerm,
          memberIds: options.memberIds,
          sharePermission: options.sharePerm,
          force: options.force
        });
        const message = `文档「${title}」已创建：${docResult.data.url}`;
        const notifyResult = await feishu.notifyUser({
          chatId: options.chatId,
          message
        });
        outputJson({
          success: true,
          data: {
            mode: 'doc',
            document: docResult.data,
            notification: notifyResult.data
          }
        });
      } else {
        const result = await feishu.notifyUser({
          chatId: options.chatId,
          message: text
        });
        outputJson({ success: true, data: { mode: 'text', ...result.data } });
      }
    } catch (err) {
      handleError(err);
    }
  });

// ---------- create-doc 命令 ----------
program
  .command('create-doc')
  .description('创建飞书文档')
  .requiredOption('-t, --title <title>', '文档标题')
  .option('-c, --content <content>', '文档内容（与 --content-file 二选一）', '')
  .option('--content-file <path>', '从文件读取文档内容（markdown），跨平台传多行内容推荐用此')
  .option('-f, --folder-token <token>', '目标文件夹 Token')
  .option('--notify-user <userId>', '创建后通知的用户 open_id')
  .option('--notify-msg <message>', '自定义通知消息')
  .option('--public', '创建后设为外部链接可编辑（默认否）', false)
  .option('--internal', '创建后设为企业内部链接可访问（默认）', false)
  .option('--private', '机密文档，仅应用创建者和授权成员可访问', false)
  .option('--link-perm <perm>', '企业内部链接权限: tenant_readable/tenant_editable')
  .option('--member-ids <ids>', '额外授权成员 open_id，逗号分隔；默认读 FEISHU_DEFAULT_MEMBER_IDS')
  .option('--share-perm <perm>', '给被通知用户的权限: view/edit/full_access', process.env.FEISHU_DEFAULT_MEMBER_PERMISSION || 'view')
  .option('--table <json>', '文档内表格（JSON 二维数组），如 [["姓名","分"],["A","90"]]')
  .option('--table-file <path>', '从 JSON 文件读取表格二维数组（与 --table 二选一）')
  .option('--force', '跳过乱码检测（默认发现 ?? / U+FFFD 会拒发）', false)
  .option('--app-id <id>', '飞书 App ID (或设环境变量 FEISHU_APP_ID)')
  .option('--app-secret <secret>', '飞书 App Secret (或设环境变量 FEISHU_APP_SECRET)')
  .action(async (options) => {
    try {
      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);

      const tableData = read2DArray(options.table, options.tableFile);
      const content = options.contentFile ? readTextFile(options.contentFile) : options.content;

      const result = await feishu.createAndNotify({
        title: options.title,
        content,
        force: options.force,
        userId: options.notifyUser,
        notifyMessage: options.notifyMsg,
        folderToken: options.folderToken,
        makePublic: options.public,
        makeInternal: options.internal,
        makePrivate: options.private,
        linkPermission: options.linkPerm,
        memberIds: options.memberIds,
        sharePermission: options.sharePerm,
        tables: tableData ? [tableData] : null
      });

      outputJson(result);
    } catch (err) {
      handleError(err);
    }
  });

// ---------- notify 命令 ----------
program
  .command('notify')
  .description('向用户发送通知消息')
  .option('-u, --user <userId>', '用户 open_id（与 --chat 二选一）')
  .option('--chat <chatId>', '群 chat_id（发给群，机器人需在群内）')
  .requiredOption('-m, --message <message>', '消息内容')
  .option('--at <open_ids>', '群内 @ 用户：逗号分隔 open_id，或 all 表示 @所有人')
  .option('--card', '发送卡片消息', false)
  .option('--app-id <id>', '飞书 App ID')
  .option('--app-secret <secret>', '飞书 App Secret')
  .action(async (options) => {
    try {
      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);

      let message = options.message;
      let msgType = 'text';

      // 如果指定了 --card，尝试解析为卡片 JSON
      if (options.card) {
        try {
          message = JSON.parse(options.message);
          msgType = 'card';
        } catch {
          // 解析失败则作为普通文本发送卡片
          message = feishu.buildDocCard({
            title: '通知',
            url: '',
            description: options.message
          });
          msgType = 'card';
        }
      }

      const result = await feishu.notifyUser({
        userId: options.user,
        chatId: options.chat,
        message,
        msgType,
        at: options.at
      });

      outputJson(result);
    } catch (err) {
      handleError(err);
    }
  });

// ---------- get-user 命令 ----------
program
  .command('get-user')
  .description('通过邮箱或手机号查询用户 open_id')
  .option('-e, --email <email>', '用户邮箱')
  .option('-m, --mobile <mobile>', '用户手机号')
  .option('--app-id <id>', '飞书 App ID')
  .option('--app-secret <secret>', '飞书 App Secret')
  .action(async (options) => {
    try {
      if (!options.email && !options.mobile) {
        throw new Error('请提供 --email 或 --mobile 至少一个参数');
      }

      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);

      const result = await feishu.getUserId({
        email: options.email,
        mobile: options.mobile
      });

      outputJson(result);
    } catch (err) {
      handleError(err);
    }
  });

// ---------- create-sheet 命令 ----------
program
  .command('create-sheet')
  .description('创建电子表格并写入二维数据（数据分析落表 / 导出）')
  .requiredOption('-t, --title <title>', '表格标题')
  .option('-d, --data <json>', '二维数据 JSON，如 [["系列","花费"],["示例","USD 100"]]')
  .option('--data-file <path>', '从 JSON 文件读取二维数据（与 --data 二选一）')
  .option('-f, --folder-token <token>', '目标文件夹 Token')
  .option('--notify-user <userId>', '创建后通知的用户 open_id')
  .option('--notify-msg <message>', '自定义通知消息')
  .option('--public', '创建后设为外部链接可编辑', false)
  .option('--internal', '创建后设为企业内部链接可访问（默认）', false)
  .option('--private', '机密表格，仅应用创建者和授权成员可访问', false)
  .option('--link-perm <perm>', '企业内部链接权限: tenant_readable/tenant_editable')
  .option('--member-ids <ids>', '额外授权成员 open_id，逗号分隔；默认读 FEISHU_DEFAULT_MEMBER_IDS')
  .option('--share-perm <perm>', '给被通知用户的权限: view/edit/full_access', process.env.FEISHU_DEFAULT_MEMBER_PERMISSION || 'view')
  .option('--force', '跳过乱码检测（默认发现 ?? / U+FFFD 会拒发）', false)
  .option('--app-id <id>', '飞书 App ID')
  .option('--app-secret <secret>', '飞书 App Secret')
  .action(async (options) => {
    try {
      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);

      const data = read2DArray(options.data, options.dataFile);

      const result = await feishu.createSheetAndNotify({
        title: options.title,
        data,
        force: options.force,
        folderToken: options.folderToken,
        userId: options.notifyUser,
        notifyMessage: options.notifyMsg,
        makePublic: options.public,
        makeInternal: options.internal,
        makePrivate: options.private,
        linkPermission: options.linkPerm,
        memberIds: options.memberIds,
        sharePermission: options.sharePerm
      });

      outputJson(result);
    } catch (err) {
      handleError(err);
    }
  });

// ---------- read-sheet 命令 ----------
program
  .command('read-sheet')
  .description('读取电子表格数据，导出为 JSON 二维数组')
  .requiredOption('-t, --token <spreadsheetToken>', '电子表格 token（URL /sheets/ 后那段）')
  .requiredOption('-s, --sheet <sheetId>', '工作表 sheet_id')
  .option('-r, --range <range>', '单元格范围', 'A1:Z1000')
  .option('--app-id <id>', '飞书 App ID')
  .option('--app-secret <secret>', '飞书 App Secret')
  .action(async (options) => {
    try {
      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);

      const range = `${options.sheet}!${options.range}`;
      const values = await feishu.api.readSheetValues(options.token, range);

      outputJson({ success: true, data: { range, values } });
    } catch (err) {
      handleError(err);
    }
  });

// ---------- append-sheet 命令 ----------
program
  .command('append-sheet')
  .description('向现有工作表末尾追加二维数据，不覆盖已有数据')
  .requiredOption('-t, --token <spreadsheetToken>', '电子表格 token（URL /sheets/ 后那段）')
  .requiredOption('-s, --sheet <sheetId>', '工作表 sheet_id（URL sheet= 后那段）')
  .option('-d, --data <json>', '二维数据 JSON，如 [["时间","人员","操作"]]')
  .option('--data-file <path>', '从 JSON 文件读取二维数据（与 --data 二选一）')
  .option('--force', '跳过乱码检测（默认发现 ?? / U+FFFD 会拒绝写入）', false)
  .option('--app-id <id>', '飞书 App ID')
  .option('--app-secret <secret>', '飞书 App Secret')
  .action(async (options) => {
    try {
      const data = readAppendData(options.data, options.dataFile);
      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);
      const result = await feishu.appendSheet({
        spreadsheetToken: options.token,
        sheetId: options.sheet,
        data,
        force: options.force
      });
      outputJson(result);
    } catch (err) {
      handleError(err);
    }
  });

// ---------- list-chats 命令 ----------
program
  .command('list-chats')
  .description('列出机器人所在的群（用于查群 chat_id）')
  .option('--app-id <id>', '飞书 App ID')
  .option('--app-secret <secret>', '飞书 App Secret')
  .action(async (options) => {
    try {
      const config = buildConfig(options);
      const feishu = new FeishuCLI(config);
      const chats = await feishu.api.listChats();
      outputJson({
        success: true,
        data: {
          count: chats.length,
          chats: chats.map(c => ({ name: c.name, chatId: c.chat_id, owner: c.owner_id }))
        }
      });
    } catch (err) {
      handleError(err);
    }
  });

// ---------- 解析命令 ----------
program.parse();
