# -*- coding: utf-8 -*-
r"""
把 Markdown 文件发布为飞书云文档，Markdown 表格会转成飞书真实表格块。

为什么不用 feishu-cli.cmd：
  1. src/index.js 的 _textToBlocks 不认 Markdown 表格，`| a | b |` 会变成一行竖线文本；
     create-doc 的 --table-file 也只支持一张表、且只能追加到文档末尾。
  2. 本机只有 Adobe 附带的 Node v16，缺少全局 fetch，src/api.js 跑不起来。
凭据仍然复用 tools/feishu-cli/.env，行为与 CLI 保持一致（默认企业内部链接可阅读）。

用法：
  python tools\feishu-cli\publish_markdown.py --file <md路径> --title "文档标题"
  可选：--folder-token <token> --private --notify-chat oc_xxx --notify-user ou_xxx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

API = 'https://open.feishu.cn/open-apis'
ENV_PATH = Path(__file__).resolve().parent / '.env'

HEADING_FIELD = {3: 'heading1', 4: 'heading2', 5: 'heading3',
                 6: 'heading4', 7: 'heading5', 8: 'heading6'}
BLOCK_FIELD = {2: 'text', 12: 'bullet', 13: 'ordered', **HEADING_FIELD}


# ---------------------------------------------------------------- 配置

def load_env(path: Path = ENV_PATH) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ---------------------------------------------------------------- Markdown 解析

INLINE_RE = re.compile(r'(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)')


def parse_inline(text: str) -> list[dict]:
    """把 **粗体**、*斜体*、`行内代码` 拆成多个带样式的 text_run。"""
    elements = []
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith('**') and part.endswith('**') and len(part) > 4:
            style, content = {'bold': True}, part[2:-2]
        elif part.startswith('`') and part.endswith('`') and len(part) > 2:
            style, content = {'inline_code': True}, part[1:-1]
        elif part.startswith('*') and part.endswith('*') and len(part) > 2:
            style, content = {'italic': True}, part[1:-1]
        else:
            style, content = None, part
        run = {'content': content}
        if style:
            run['text_element_style'] = style
        elements.append({'text_run': run})
    return elements or [{'text_run': {'content': ''}}]


def strip_markers(text: str) -> str:
    """表格单元格只能放纯文本，去掉 Markdown 标记。"""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    return text.strip()


def is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith('|') and s.endswith('|') and len(s) > 2


def is_table_separator(line: str) -> bool:
    """匹配 | --- | :---: | 这类分隔行；必须先去掉所有竖线再判断字符集。"""
    s = line.strip().strip('|').replace('|', '').strip()
    return bool(s) and set(s) <= set('-: ')


def split_row(line: str) -> list[str]:
    return [strip_markers(c) for c in line.strip().strip('|').split('|')]


def parse_markdown(md: str) -> list[tuple[str, object]]:
    """返回有序的段列表：('blocks', [block...]) 或 ('table', [[cell...]...])。"""
    lines = md.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    segments: list[tuple[str, object]] = []
    pending: list[dict] = []
    i = 0

    def flush():
        nonlocal pending
        if pending:
            segments.append(('blocks', pending))
            pending = []

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if not line or re.fullmatch(r'-{3,}|\*{3,}|_{3,}', line):
            i += 1
            continue

        # 表格：连续的 | ... | 行
        if is_table_row(line):
            rows = []
            while i < len(lines) and is_table_row(lines[i]):
                if not is_table_separator(lines[i]):
                    rows.append(split_row(lines[i]))
                i += 1
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [''] * (width - len(r)) for r in rows]
                flush()
                segments.append(('table', rows))
            continue

        # 代码块
        if line.startswith('```'):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            i += 1
            pending.append({
                'block_type': 14,
                'code': {'elements': [{'text_run': {'content': '\n'.join(code)}}],
                         'style': {'language': 1}},
            })
            continue

        # 标题 / 列表 / 段落
        block_type, content = 2, line
        for level, prefix in enumerate(['# ', '## ', '### ', '#### ', '##### ', '###### '], start=3):
            if content.startswith(prefix):
                block_type, content = level, content[len(prefix):]
                break
        else:
            if re.match(r'^[-*]\s+', content):
                block_type, content = 12, re.sub(r'^[-*]\s+', '', content)
            elif re.match(r'^\d+\.\s+', content):
                block_type, content = 13, re.sub(r'^\d+\.\s+', '', content)
            elif content.startswith('> '):
                content = content[2:]

        pending.append({'block_type': block_type,
                        BLOCK_FIELD[block_type]: {'elements': parse_inline(content)}})
        i += 1

    flush()
    return segments


def drop_styles(blocks: list[dict]) -> list[dict]:
    """去掉行内样式，用于样式字段被拒时的降级重试。"""
    plain = json.loads(json.dumps(blocks))
    for b in plain:
        for field in b.values():
            if isinstance(field, dict):
                for el in field.get('elements', []):
                    el.get('text_run', {}).pop('text_element_style', None)
    return plain


# ---------------------------------------------------------------- 飞书 API

class Feishu:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token = None
        self._expire = 0

    def token(self) -> str:
        if self._token and time.time() < self._expire:
            return self._token
        r = requests.post(f'{API}/auth/v3/tenant_access_token/internal',
                          json={'app_id': self.app_id, 'app_secret': self.app_secret},
                          timeout=15)
        d = r.json()
        if d.get('code') != 0:
            raise RuntimeError(f"获取 token 失败: {d.get('msg')} (code {d.get('code')})")
        self._token = d['tenant_access_token']
        self._expire = time.time() + d.get('expire', 7200) - 300
        return self._token

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        r = requests.request(method, f'{API}{path}',
                             headers={'Authorization': f'Bearer {self.token()}',
                                      'Content-Type': 'application/json; charset=utf-8'},
                             data=json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload else None,
                             timeout=40)
        d = r.json()
        if d.get('code') != 0:
            raise RuntimeError(f"{method} {path} 失败: {d.get('msg')} (code {d.get('code')})")
        return d.get('data', {})

    def create_doc(self, title: str, folder_token: str | None) -> str:
        body = {'title': title}
        if folder_token:
            body['folder_token'] = folder_token
        data = self.call('POST', '/docx/v1/documents', body)
        doc_id = (data.get('document') or {}).get('document_id') or data.get('document_id')
        if not doc_id:
            raise RuntimeError('创建文档失败：未返回 document_id')
        return doc_id

    def append_blocks(self, doc_id: str, blocks: list[dict]) -> None:
        """飞书单次最多 50 个 children，需要分批；不传 index 表示追加到末尾。"""
        path = f'/docx/v1/documents/{doc_id}/blocks/{doc_id}/children'
        for start in range(0, len(blocks), 50):
            batch = blocks[start:start + 50]
            try:
                self.call('POST', path, {'children': batch})
            except RuntimeError:
                self.call('POST', path, {'children': drop_styles(batch)})

    def append_table(self, doc_id: str, rows: list[list[str]]) -> None:
        n_rows, n_cols = len(rows), max(len(r) for r in rows)
        prefix = f'tbl_{int(time.time() * 1000)}_{n_rows}x{n_cols}'
        cell_ids = [f'{prefix}_c{i}' for i in range(n_rows * n_cols)]
        text_ids = [f'{prefix}_t{i}' for i in range(n_rows * n_cols)]

        descendants = [{
            'block_id': prefix,
            'block_type': 31,
            'table': {'property': {'row_size': n_rows, 'column_size': n_cols,
                                   'header_row': True}},
            'children': cell_ids,
        }]
        for i in range(n_rows * n_cols):
            r, c = divmod(i, n_cols)
            descendants.append({'block_id': cell_ids[i], 'block_type': 32,
                                'table_cell': {}, 'children': [text_ids[i]]})
            descendants.append({'block_id': text_ids[i], 'block_type': 2,
                                'text': {'elements': [{'text_run': {'content': str(rows[r][c])}}]},
                                'children': []})

        self.call('POST',
                  f'/docx/v1/documents/{doc_id}/blocks/{doc_id}/descendant?document_revision_id=-1',
                  {'children_id': [prefix], 'descendants': descendants})

    def set_internal(self, token: str, link_perm: str = 'tenant_readable') -> None:
        self.call('PATCH', f'/drive/v1/permissions/{token}/public?type=docx', {
            'external_access': False, 'external_access_entity': 'closed',
            'security_entity': 'anyone_can_view', 'comment_entity': 'anyone_can_view',
            'share_entity': 'same_tenant', 'link_share_entity': link_perm,
            'invite_external': False,
        })

    def set_private(self, token: str) -> None:
        self.call('PATCH', f'/drive/v1/permissions/{token}/public?type=docx', {
            'external_access': False, 'external_access_entity': 'closed',
            'security_entity': 'only_full_access', 'comment_entity': 'anyone_can_view',
            'share_entity': 'same_tenant', 'link_share_entity': 'closed',
            'invite_external': False,
        })

    def add_member(self, token: str, open_id: str, perm: str = 'view') -> None:
        self.call('POST', f'/drive/v1/permissions/{token}/members?type=docx',
                  {'member_type': 'openid', 'member_id': open_id, 'perm': perm})

    def delete_doc(self, token: str) -> None:
        """把文档移入回收站（用于重发时清理旧版本）。"""
        self.call('DELETE', f'/drive/v1/files/{token}?type=docx')

    def send_text(self, receive_id: str, text: str) -> None:
        id_type = 'chat_id' if receive_id.startswith('oc_') else 'open_id'
        self.call('POST', f'/im/v1/messages?receive_id_type={id_type}',
                  {'receive_id': receive_id, 'msg_type': 'text',
                   'content': json.dumps({'text': text}, ensure_ascii=False)})


# ---------------------------------------------------------------- 入口

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True, help='Markdown 文件路径')
    ap.add_argument('--title', help='文档标题，默认取 Markdown 第一个 # 标题')
    ap.add_argument('--folder-token', help='目标文件夹，默认读 .env')
    ap.add_argument('--private', action='store_true', help='仅授权成员可见')
    ap.add_argument('--member-ids', help='额外授权的 open_id，逗号分隔')
    ap.add_argument('--notify-chat', help='创建后把链接发到群 chat_id')
    ap.add_argument('--notify-user', help='创建后把链接私聊发给 open_id')
    args = ap.parse_args()

    env = load_env()
    app_id, app_secret = env.get('FEISHU_APP_ID'), env.get('FEISHU_APP_SECRET')
    if not app_id or not app_secret:
        print(json.dumps({'success': False, 'error': '.env 缺少 FEISHU_APP_ID / FEISHU_APP_SECRET'},
                         ensure_ascii=False))
        return 1

    md = Path(args.file).read_text(encoding='utf-8-sig')
    if '\ufffd' in md or '??' in md:
        print(json.dumps({'success': False, 'error': '源文件疑似乱码（含 U+FFFD 或 ??），已拒绝发布'},
                         ensure_ascii=False))
        return 1

    title = args.title
    if not title:
        m = re.search(r'^#\s+(.+)$', md, re.M)
        title = m.group(1).strip() if m else Path(args.file).stem
    # 首个 H1 会成为文档标题，正文里去掉避免重复
    md = re.sub(r'^#\s+.+\n', '', md, count=1)

    segments = parse_markdown(md)
    n_tables = sum(1 for kind, _ in segments if kind == 'table')
    n_blocks = sum(len(payload) for kind, payload in segments if kind == 'blocks')

    fs = Feishu(app_id, app_secret)
    doc_id = fs.create_doc(title, args.folder_token or env.get('FEISHU_DEFAULT_FOLDER_TOKEN'))

    for kind, payload in segments:
        if kind == 'blocks':
            fs.append_blocks(doc_id, payload)
        else:
            fs.append_table(doc_id, payload)

    url = f'https://www.feishu.cn/docx/{doc_id}'
    warnings = []
    try:
        if args.private or env.get('FEISHU_DEFAULT_SHARE_MODE') == 'private':
            fs.set_private(doc_id)
        else:
            fs.set_internal(doc_id, env.get('FEISHU_INTERNAL_LINK_PERMISSION') or 'tenant_readable')
    except RuntimeError as e:
        warnings.append(f'设置共享范围失败: {e}')

    members = [m.strip() for m in (args.member_ids or env.get('FEISHU_DEFAULT_MEMBER_IDS') or '').split(',') if m.strip()]
    for m in members:
        try:
            fs.add_member(doc_id, m, env.get('FEISHU_DEFAULT_MEMBER_PERMISSION') or 'view')
        except RuntimeError as e:
            warnings.append(f'为 {m} 授权失败: {e}')

    for target in filter(None, [args.notify_chat, args.notify_user]):
        try:
            fs.send_text(target, f'文档「{title}」已创建：{url}')
        except RuntimeError as e:
            warnings.append(f'通知 {target} 失败: {e}')

    result = {'success': True, 'data': {'documentToken': doc_id, 'url': url, 'title': title,
                                        'blocks': n_blocks, 'tables': n_tables}}
    if warnings:
        result['data']['warnings'] = warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
