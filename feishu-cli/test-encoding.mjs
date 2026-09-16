// 编码模块自测：node test-encoding.mjs
import { writeFileSync, unlinkSync, mkdtempSync, existsSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { execSync } from 'child_process';
import { readTextFileSmart, findMojibake } from './src/encoding.js';

const dir = mkdtempSync(join(tmpdir(), 'feishu-enc-'));
const zh = '# Demo report ABC-123\n\n- spend: USD 100\n- note: 中文编码应保持完整。\n';
let pass = 0, fail = 0;

function check(name, cond, extra = '') {
  if (cond) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}  ${extra}`); }
}

// 1. UTF-8 无 BOM
let p = join(dir, 'utf8.md');
writeFileSync(p, zh, 'utf8');
check('UTF-8 读取', readTextFileSmart(p) === zh);

// 2. UTF-8 带 BOM
p = join(dir, 'utf8bom.md');
writeFileSync(p, '\uFEFF' + zh, 'utf8');
check('UTF-8 BOM 读取', readTextFileSmart(p) === zh);

// 3. UTF-16 LE 带 BOM（PowerShell 5 重定向默认）
p = join(dir, 'utf16le.md');
writeFileSync(p, Buffer.concat([Buffer.from([0xFF, 0xFE]), Buffer.from(zh, 'utf16le')]));
check('UTF-16 LE BOM 读取', readTextFileSmart(p) === zh);

// 4. UTF-16 LE 无 BOM
p = join(dir, 'utf16le-nobom.md');
writeFileSync(p, Buffer.from(zh, 'utf16le'));
check('UTF-16 LE 无 BOM 读取', readTextFileSmart(p) === zh);

// 5. GBK（中文 Windows ANSI），用 iconv 场景模拟：手工构造 GBK 字节
const gbkBytes = (() => {
  // "中文测试" 的 GBK 编码
  return Buffer.from([0xD6, 0xD0, 0xCE, 0xC4, 0xB2, 0xE2, 0xCA, 0xD4]);
})();
p = join(dir, 'gbk.md');
writeFileSync(p, gbkBytes);
check('GBK 读取', readTextFileSmart(p) === '中文测试', JSON.stringify(readTextFileSmart(p)));

// 6. 乱码检测：连续问号
check('检测 ??', findMojibake('示例 ???? 实验') !== null);
// 7. 乱码检测：U+FFFD
check('检测 U+FFFD', findMojibake('示例 \uFFFD 实验') !== null);
// 8. 乱码检测：问号贴中文
check('检测中文旁问号', findMojibake('花费?元') !== null);
// 9. 正常内容不误报
check('正常中文不误报', findMojibake(zh) === null);
// 10. 正常英文问句不误报
check('英文问句不误报', findMojibake('What is ROAS? It is return on ad spend.') === null);
// 11. 真实历史乱码文件存在时才校验；便携 CLI 包通常不附带该项目输出目录
const historicalFile = '../../outputs/encoding-sample/mojibake.md';
if (existsSync(historicalFile)) {
  check('历史乱码文件被拦截', findMojibake(readTextFileSmart(historicalFile)) !== null);
} else {
  console.log('SKIP  历史乱码文件未随便携 CLI 提供');
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
