/**
 * 文本编码与乱码防护工具
 *
 * 背景：Windows 上源文件可能被以 GBK / UTF-16 / ANSI 编码写坏，
 * 中文会变成 "??"，之前已经多次把乱码发进飞书文档。
 * 这里统一做两件事：
 *   1) 读文件时自动识别编码（UTF-8 BOM / UTF-16 LE/BE / GBK 回退）；
 *   2) 写飞书文档/表格前检测疑似乱码，发现问题直接报错拒发。
 */

import { readFileSync } from 'fs';

/** 统计 buffer 前段的 NUL 字节占比，用于识别无 BOM 的 UTF-16 */
function nulRatio(buf) {
  const n = Math.min(buf.length, 2000);
  if (n === 0) return 0;
  let zeros = 0;
  for (let i = 0; i < n; i++) {
    if (buf[i] === 0) zeros++;
  }
  return zeros / n;
}

/**
 * 把文件 buffer 解码成字符串，自动识别编码：
 * UTF-16 LE/BE BOM -> UTF-8 BOM -> 严格 UTF-8 -> GBK -> 宽松 UTF-8 兜底
 */
export function decodeTextBuffer(buf) {
  if (buf.length >= 2 && buf[0] === 0xFF && buf[1] === 0xFE) {
    return buf.subarray(2).toString('utf16le');
  }
  if (buf.length >= 2 && buf[0] === 0xFE && buf[1] === 0xFF) {
    const swapped = Buffer.from(buf.subarray(2));
    swapped.swap16();
    return swapped.toString('utf16le');
  }
  if (buf.length >= 3 && buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF) {
    return buf.subarray(3).toString('utf8');
  }
  // 无 BOM 的 UTF-16 LE（PowerShell 5 重定向常见）
  if (nulRatio(buf) > 0.3) {
    return buf.toString('utf16le');
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buf);
  } catch {
    // 非合法 UTF-8：按 GBK 解（中文 Windows 常见），失败再宽松 UTF-8 兜底
    try {
      return new TextDecoder('gbk', { fatal: true }).decode(buf);
    } catch {
      return buf.toString('utf8');
    }
  }
}

/** 读取文本文件并自动识别编码、去 BOM */
export function readTextFileSmart(filePath) {
  let s = decodeTextBuffer(readFileSync(filePath));
  if (s.charCodeAt(0) === 0xFEFF) s = s.slice(1);
  return s;
}

/**
 * 检测文本是否疑似乱码，返回问题描述；正常返回 null。
 * 判定规则：
 *   - 含 Unicode 替换字符 U+FFFD（解码失败的典型产物）
 *   - 含连续 2 个以上半角问号（中文被 "?" 替换的典型产物）
 *   - 半角问号紧邻中文/全角字符（部分字符被替换）
 */
export function findMojibake(text) {
  if (!text) return null;
  if (text.includes('\uFFFD')) {
    return '包含 Unicode 替换字符 U+FFFD（文件曾被错误编码解码）';
  }
  const run = text.match(/\?{2,}/);
  if (run) {
    const idx = text.indexOf(run[0]);
    const ctx = text.slice(Math.max(0, idx - 20), idx + run[0].length + 20).replace(/\n/g, ' ');
    return `包含连续问号 "${run[0]}"（上下文: ...${ctx}...）`;
  }
  const nearCjk = text.match(/[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef]\?|\?[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef]/);
  if (nearCjk) {
    const idx = text.indexOf(nearCjk[0]);
    const ctx = text.slice(Math.max(0, idx - 20), idx + 22).replace(/\n/g, ' ');
    return `半角问号紧邻中文字符 "${nearCjk[0]}"（上下文: ...${ctx}...）`;
  }
  return null;
}

/**
 * 发布前的乱码断言：发现疑似乱码直接抛错，阻止把坏内容写进飞书。
 * @param {string} text - 待检查文本
 * @param {string} label - 出错时提示的内容来源（如 "文档内容"）
 * @param {boolean} allow - true 时跳过检查（--force）
 */
export function assertCleanText(text, label, allow = false) {
  if (allow) return;
  const problem = findMojibake(typeof text === 'string' ? text : JSON.stringify(text));
  if (problem) {
    throw new Error(
      `${label}疑似乱码，已拒绝写入飞书：${problem}。` +
      '请检查源文件是否为 UTF-8 编码（Windows 写文件必须显式指定 UTF-8），重建源文件后重试；' +
      '如果确认内容本来就含连续问号，可加 --force 跳过检查。'
    );
  }
}
