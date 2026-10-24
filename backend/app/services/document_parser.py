"""Bounded, network-free structured reading. Never promises Office page fidelity."""
from __future__ import annotations

import base64
import posixpath
import re
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

PARSER_VERSION = 'structured-1'
MAX_BYTES = 80 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_PART = 8 * 1024 * 1024
MAX_BLOCKS = 20000
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


class _Content:
    def __init__(self):
        self.blocks: list[dict] = []
        self.warnings: list[str] = []
        self.image_bytes = 0

    def add(self, kind: str, text: str = '', **extra):
        if len(self.blocks) >= MAX_BLOCKS:
            raise ValueError('资料内容过多，请分成较小文件导入')
        self.blocks.append({'id': f'b{len(self.blocks) + 1}', 'kind': kind,
                            'text': text, **extra})

    def unsupported(self, message: str, **extra):
        self.add('unsupported', message, **extra)
        if message not in self.warnings:
            self.warnings.append(message)


def _decode(data: bytes, encoding: str) -> str:
    if encoding not in {'auto', 'utf-8', 'gb18030', 'utf-16'}:
        raise ValueError('不支持此编码，请选择 UTF-8 或 GB18030')
    codec = ('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig') if encoding == 'auto' else encoding
    try:
        text = data.decode(codec, errors='strict').replace('\r\n', '\n').replace('\r', '\n')
    except UnicodeError as exc:
        raise ValueError('无法确定文字编码，请选择 GB18030 或 UTF-8 后重试') from exc
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text):
        raise ValueError('文件包含二进制内容，不是可读文本')
    return text


def _text(content: _Content, text: str, markdown: bool):
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if markdown and line.startswith(('```', '~~~')):
            fence = line[:3]
            code = []
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code.append(lines[index]); index += 1
            index += 1
            content.add('code', '\n'.join(code))
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)$', line) if markdown else None
        if heading:
            content.add('heading', heading[2], level=len(heading[1]))
        elif re.match(r'^第[一二三四五六七八九十百\d]+[章节篇]\s*\S*$', line) and len(line) < 80:
            content.add('heading', line, level=1)
        elif markdown and '|' in line and index < len(lines) and re.fullmatch(r'[\s|:\-]+', lines[index]) and '-' in lines[index]:
            cells = [[cell.strip() for cell in line.strip('|').split('|')]]
            index += 1
            while index < len(lines) and '|' in lines[index] and lines[index].strip():
                cells.append([cell.strip() for cell in lines[index].strip().strip('|').split('|')]); index += 1
            content.add('table', '\n'.join(' | '.join(row) for row in cells), cells=cells)
        else:
            if markdown and re.search(r'!\[.*?\]\(', line):
                content.unsupported('图片未导入：为保护本地资料，不自动加载外部或本机路径中的图片。')
            # Rendering is always Vue-escaped text; HTML and links are inert.
            kind = 'list' if markdown and re.match(r'^(?:[-*+] |\d+[.)] )', line) else 'paragraph'
            # Bounded blocks keep search and retrieval payloads small.
            for start in range(0, len(line), 2000):
                content.add(kind, line[start:start + 2000])


class _Office:
    def __init__(self, data: bytes):
        self.zip = ZipFile(BytesIO(data))
        members = self.zip.infolist()
        names = [m.filename for m in members]
        if len(members) > 5000 or len(set(names)) != len(names) or sum(m.file_size for m in members) > MAX_EXPANDED:
            self.zip.close()
            raise ValueError('文档解压后过大或结构重复，请另存为较小文件')
        for member in members:
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.filename or ':' in member.filename
                    or member.flag_bits & 1 or member.file_size > MAX_PART
                    or 'vbaproject' in member.filename.lower()):
                self.zip.close()
                raise ValueError('文档含有不支持的加密、宏或异常路径')

    def read(self, name: str) -> bytes:
        with self.zip.open(name) as stream:
            data = stream.read(MAX_PART + 1)
        if len(data) > MAX_PART:
            raise ValueError('文档内部内容过大')
        return data

    def xml(self, name: str):
        data = self.read(name)
        # XML encoded as UTF-16 must receive the same entity/DTD check.
        scan = data.replace(b'\x00', b'').lower()
        if b'<!doctype' in scan or b'<!entity' in scan:
            raise ValueError('文档包含不支持的 XML 实体')
        return ET.fromstring(data)

    def relations(self, part: str) -> dict[str, str | None]:
        path = PurePosixPath(part)
        rel_path = str(path.parent / '_rels' / (path.name + '.rels'))
        if rel_path not in self.zip.namelist():
            return {}
        results = {}
        for rel in self.xml(rel_path):
            target = rel.get('Target', '')
            if rel.get('TargetMode') == 'External' or ':' in target or '\\' in target:
                results[rel.get('Id')] = None
                continue
            full = posixpath.normpath(posixpath.join(str(path.parent), target))
            if target.startswith('/') or full.startswith('../') or full not in self.zip.namelist():
                results[rel.get('Id')] = None
            else:
                results[rel.get('Id')] = full
        return results

    def images(self, element, part: str, content: _Content, **extra):
        rels = self.relations(part)
        for blip in element.iter(f'{{{A}}}blip'):
            target = rels.get(blip.get(f'{{{R}}}embed', ''))
            if not target:
                content.unsupported('图片无法读取或为外部资源，请对照原文件。', **extra)
                continue
            raw = self.read(target)
            mime = ('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
                    'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else
                    'image/gif' if raw.startswith((b'GIF87a', b'GIF89a')) else
                    'image/webp' if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP' else None)
            if not mime or len(raw) > 2 * 1024 * 1024 or content.image_bytes + len(raw) > 16 * 1024 * 1024:
                content.unsupported('此图片格式或大小暂不支持，请对照原文件。', **extra)
            else:
                content.image_bytes += len(raw)
                content.add('image', '', image=f'data:{mime};base64,{base64.b64encode(raw).decode()}', **extra)


def _runs(element, namespace: str) -> str:
    parts = []
    for node in element.iter():
        if node.tag == f'{{{namespace}}}t':
            parts.append(node.text or '')
        elif node.tag in {f'{{{namespace}}}br', f'{{{namespace}}}tab'}:
            parts.append('\n' if node.tag.endswith('br') else '\t')
    return ''.join(parts).strip()


def _docx(office: _Office, content: _Content):
    part = 'word/document.xml'
    body = office.xml(part).find(f'{{{W}}}body')
    if body is None:
        raise ValueError('Word 文档没有可读取的正文')
    styles = {}
    if 'word/styles.xml' in office.zip.namelist():
        for style in office.xml('word/styles.xml').findall(f'{{{W}}}style'):
            level = style.find(f'.//{{{W}}}outlineLvl')
            if level is not None:
                styles[style.get(f'{{{W}}}styleId')] = min(6, int(level.get(f'{{{W}}}val', '0')) + 1)
    for element in body:
        if element.tag == f'{{{W}}}tbl':
            cells = [[_runs(cell, W) for cell in row.findall(f'{{{W}}}tc')] for row in element.findall(f'{{{W}}}tr')]
            content.add('table', '\n'.join(' | '.join(row) for row in cells), cells=cells)
            office.images(element, part, content)
            continue
        if element.tag != f'{{{W}}}p':
            if element.tag != f'{{{W}}}sectPr':
                content.unsupported('此对象暂不能完整显示，请对照原文件。')
            continue
        text = _runs(element, W)
        style = element.find(f'{{{W}}}pPr/{{{W}}}pStyle')
        style_name = style.get(f'{{{W}}}val', '') if style is not None else ''
        match = re.search(r'(?:heading|标题)\s*([1-6])', style_name, re.I)
        level = styles.get(style_name) or (int(match[1]) if match else None)
        if text:
            kind = 'heading' if level else 'list' if element.find(f'.//{{{W}}}numPr') is not None else 'paragraph'
            content.add(kind, text, **({'level': level} if level else {}))
        office.images(element, part, content)
        if any(node.tag.rsplit('}', 1)[-1] in {'oMath', 'oMathPara', 'object', 'pict'} for node in element.iter()):
            content.unsupported('公式或嵌入对象需要核对，请对照原文件，不要仅凭提取文字计算。')


def _pptx(office: _Office, content: _Content):
    part = 'ppt/presentation.xml'
    root = office.xml(part)
    rels = office.relations(part)
    slides = root.findall(f'.//{{{P}}}sldId')
    if not slides or len(slides) > 2000:
        raise ValueError('演示文稿没有幻灯片或幻灯片过多')
    for number, slide in enumerate(slides, 1):
        target = rels.get(slide.get(f'{{{R}}}id'))
        if not target:
            raise ValueError('幻灯片来源不完整')
        tree = office.xml(target).find(f'.//{{{P}}}spTree')
        if tree is None:
            content.add('heading', f'幻灯片 {number}', level=1, slide=number)
            continue
        title = None
        for shape in tree.iter(f'{{{P}}}sp'):
            placeholder = shape.find(f'.//{{{P}}}ph')
            if placeholder is not None and placeholder.get('type') in {'title', 'ctrTitle'}:
                title = _runs(shape, A)
                break
        content.add('heading', title or f'幻灯片 {number}', level=1, slide=number)
        for shape in tree.iter():
            if shape.tag == f'{{{P}}}sp':
                text = _runs(shape, A)
                if text and text != title:
                    content.add('paragraph', text, slide=number)
            elif shape.tag == f'{{{A}}}tbl':
                cells = [[_runs(cell, A) for cell in row.findall(f'{{{A}}}tc')] for row in shape.findall(f'{{{A}}}tr')]
                content.add('table', '\n'.join(' | '.join(row) for row in cells), cells=cells, slide=number)
            elif shape.tag.rsplit('}', 1)[-1] in {'oleObj', 'chart', 'relIds', 'oMath'}:
                content.unsupported('此幻灯片含复杂对象，请对照原文件；动画与复杂公式不在结构化阅读范围。', slide=number)
        office.images(tree, target, content, slide=number)


def parse_document(data: bytes, filename: str, encoding: str = 'auto') -> dict:
    if not data or len(data) > MAX_BYTES:
        raise ValueError('文件为空或超过 80 MB')
    suffix = PurePosixPath(filename.replace('\\', '/')).suffix.lower().lstrip('.')
    if suffix not in {'txt', 'md', 'docx', 'pptx'}:
        raise ValueError('请选择 PDF、DOCX、PPTX、TXT 或 MD；旧版 DOC/PPT 请先另存为新版格式')
    content = _Content()
    if suffix in {'txt', 'md'}:
        _text(content, _decode(data, encoding), suffix == 'md')
    else:
        office = None
        try:
            office = _Office(data)
            (_docx if suffix == 'docx' else _pptx)(office, content)
        except (BadZipFile, ET.ParseError, KeyError, RuntimeError, OverflowError) as exc:
            raise ValueError('文件结构损坏或不受支持，请另存为 DOCX/PPTX 后重试') from exc
        finally:
            if office is not None:
                office.zip.close()
    if not content.blocks:
        raise ValueError('没有找到可阅读内容')
    return {'format': suffix, 'blocks': content.blocks, 'warnings': content.warnings,
            'parser_version': PARSER_VERSION}
