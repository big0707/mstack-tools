import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import FeishuAPI from './src/api.js';

const here = dirname(fileURLToPath(import.meta.url));

test('appendSheetValues 调用 values_append 并强制 INSERT_ROWS', async () => {
  const api = new FeishuAPI({ appId: 'test-app', appSecret: 'test-secret' });
  let captured;
  api.request = async (path, options, requestOptions) => {
    captured = { path, options, requestOptions };
    return {
      revision: 12,
      tableRange: 'IQjAfq!A1:C5',
      updates: { updatedRange: 'IQjAfq!A4:C5', updatedRows: 2 }
    };
  };

  const values = [
    ['2026-09-03', 'user@example.com', '新增'],
    ['2026-09-03', 'user@example.com', '删除']
  ];
  const result = await api.appendSheetValues('shtcn_token', 'IQjAfq', values);

  assert.equal(
    captured.path,
    '/sheets/v2/spreadsheets/shtcn_token/values_append?insertDataOption=INSERT_ROWS'
  );
  assert.equal(captured.options.method, 'POST');
  assert.deepEqual(captured.requestOptions, { networkRetries: 0, uncertainWrite: true });
  assert.deepEqual(JSON.parse(captured.options.body), {
    valueRange: { range: 'IQjAfq', values }
  });
  assert.equal(result.updates.updatedRows, 2);
});

test('appendSheetValues 网络结果不确定时不自动重试', async () => {
  const api = new FeishuAPI({ appId: 'test-app', appSecret: 'test-secret' });
  api.accessToken = 'test-token';
  api.tokenExpireAt = Date.now() + 60000;

  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    throw new TypeError('fetch failed');
  };

  try {
    await assert.rejects(
      () => api.appendSheetValues('token', 'IQjAfq', [['stable-record-id', '新增']]),
      /追加请求结果不确定.*不要直接重试.*read-sheet/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls, 1);
});

test('appendSheetValues 遇到 5xx/429 时不自动重试', async () => {
  const originalFetch = globalThis.fetch;

  try {
    for (const status of [503, 429]) {
      const api = new FeishuAPI({ appId: 'test-app', appSecret: 'test-secret' });
      api.accessToken = 'test-token';
      api.tokenExpireAt = Date.now() + 60000;
      let calls = 0;
      globalThis.fetch = async () => {
        calls++;
        return {
          status,
          text: async () => JSON.stringify({ code: 1, msg: 'temporary failure' })
        };
      };

      await assert.rejects(
        () => api.appendSheetValues('token', 'IQjAfq', [['stable-record-id', '新增']]),
        new RegExp(`追加请求结果不确定 \\(HTTP ${status}\\).*不要直接重试`)
      );
      assert.equal(calls, 1);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('appendSheetValues 在发请求前拒绝无效二维数据', async () => {
  const api = new FeishuAPI({ appId: 'test-app', appSecret: 'test-secret' });
  let requested = false;
  api.request = async () => { requested = true; };

  await assert.rejects(() => api.appendSheetValues('token', 'IQjAfq', []), /非空二维数组/);
  await assert.rejects(() => api.appendSheetValues('token', 'bad!sheet', [['x']]), /sheet_id 格式无效/);
  await assert.rejects(() => api.appendSheetValues('token', 'IQjAfq', [[]]), /必须是非空数组/);
  assert.equal(requested, false);
});

test('CLI help 暴露 append-sheet 所需参数', () => {
  const help = execFileSync(
    process.execPath,
    [join(here, 'src', 'cli.js'), 'append-sheet', '--help'],
    { cwd: here, encoding: 'utf8' }
  );
  assert.match(help, /--token <spreadsheetToken>/);
  assert.match(help, /--sheet <sheetId>/);
  assert.match(help, /--data <json>/);
  assert.match(help, /--data-file <path>/);
});
