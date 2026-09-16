# -*- coding: utf-8 -*-
"""回读飞书文档，确认标题、正文与表格没有编码损坏。结果写入 UTF-8 文件，避免控制台代码页干扰。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish_markdown import Feishu, load_env  # noqa: E402

doc_id = sys.argv[1]
out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name('verify_doc_out.txt')

env = load_env()
fs = Feishu(env['FEISHU_APP_ID'], env['FEISHU_APP_SECRET'])

meta = fs.call('GET', f'/docx/v1/documents/{doc_id}')
title = (meta.get('document') or {}).get('title')

blocks, page_token = [], None
while True:
    path = f'/docx/v1/documents/{doc_id}/blocks?page_size=500'
    if page_token:
        path += f'&page_token={page_token}'
    data = fs.call('GET', path)
    blocks.extend(data.get('items', []))
    if not data.get('has_more'):
        break
    page_token = data.get('page_token')

TYPE_NAME = {2: '段落', 3: 'H1', 4: 'H2', 5: 'H3', 6: 'H4',
             12: '项目符号', 13: '编号', 14: '代码块', 31: '表格', 32: '单元格'}
FIELD = {2: 'text', 3: 'heading1', 4: 'heading2', 5: 'heading3', 6: 'heading4',
         12: 'bullet', 13: 'ordered', 14: 'code'}

lines = [f'文档标题: {title}', f'文档ID: {doc_id}', f'块总数: {len(blocks)}', '']

counts = {}
for b in blocks:
    t = b.get('block_type')
    counts[t] = counts.get(t, 0) + 1
lines.append('块类型统计:')
for t, n in sorted(counts.items()):
    lines.append(f'  {TYPE_NAME.get(t, t)} (type {t}): {n}')

tables = [b for b in blocks if b.get('block_type') == 31]
lines.append(f'\n表格数: {len(tables)}')
for idx, tb in enumerate(tables, 1):
    prop = (tb.get('table') or {}).get('property', {})
    lines.append(f'  表{idx}: {prop.get("row_size")} 行 × {prop.get("column_size")} 列')

lines.append('\n' + '=' * 70)
lines.append('正文顺序抽样（前 60 个非单元格块）')
lines.append('=' * 70)
shown = 0
by_id = {b.get('block_id'): b for b in blocks}
for b in blocks:
    t = b.get('block_type')
    if t == 32 or shown >= 60:
        continue
    if t == 31:
        prop = (b.get('table') or {}).get('property', {})
        first_cells = []
        for cid in (b.get('children') or [])[:prop.get('column_size', 0)]:
            cell = by_id.get(cid, {})
            for tid in cell.get('children', []) or []:
                tblk = by_id.get(tid, {})
                txt = ''.join(e.get('text_run', {}).get('content', '')
                              for e in (tblk.get('text') or {}).get('elements', []))
                first_cells.append(txt)
        lines.append(f'[表格 {prop.get("row_size")}×{prop.get("column_size")}] 表头: {" | ".join(first_cells)}')
        shown += 1
        continue
    field = FIELD.get(t)
    if not field:
        continue
    payload = b.get(field) or {}
    txt = ''.join(e.get('text_run', {}).get('content', '') for e in payload.get('elements', []))
    if txt.strip():
        lines.append(f'[{TYPE_NAME.get(t, t)}] {txt}')
        shown += 1

report = '\n'.join(lines)
out_path.write_text(report, encoding='utf-8')
print(f'written -> {out_path}')
