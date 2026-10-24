"""Fixtures are tiny hand-authored OOXML packages, not personal documents."""
import base64
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest


def package(files):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j/ZkAAAAASUVORK5CYII=')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'


def docx_bytes():
    return package({
        '[Content_Types].xml': '<Types/>',
        'word/document.xml': f'''<w:document xmlns:w="{W}" xmlns:a="{A}" xmlns:r="{R}"><w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章 正数和负数</w:t></w:r></w:p>
        <w:p><w:r><w:t>负数小于零，正数大于零。</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>温度</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>-3℃</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:p><w:r><w:drawing><a:blip r:embed="img1"/></w:drawing></w:r></w:p>
        <w:p><w:r><w:object/></w:r></w:p></w:body></w:document>''',
        'word/_rels/document.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="img1" Target="media/image1.png" Type="{R}/image"/></Relationships>',
        'word/media/image1.png': PNG,
    })


def pptx_bytes():
    # Deliberately reverse numeric filenames: presentation relationships own order.
    return package({
        '[Content_Types].xml': '<Types/>',
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="r2"/><p:sldId id="257" r:id="r1"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="r2" Target="slides/slide2.xml" Type="{R}/slide"/><Relationship Id="r1" Target="slides/slide1.xml" Type="{R}/slide"/></Relationships>',
        'ppt/slides/slide2.xml': f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>认识分数</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>把一个整体平均分成若干份</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
    })


def parse(data, name, **kwargs):
    from app.services import document_parser
    return document_parser.parse_document(data, name, **kwargs)


def test_markdown_preserves_formula_code_table_and_disables_remote_resources():
    result = parse('# 幂运算\n\n(-1)^4=1\n\n|项|值|\n|---|---|\n|幂|4|\n\n```html\n<script>alert(1)</script>\n```\n![图片](https://evil.example/x)'.encode(), '笔记.md')
    blocks = result['blocks']
    assert result['format'] == 'md'
    assert blocks[0]['kind'] == 'heading' and blocks[0]['text'] == '幂运算'
    assert any(b['text'] == '(-1)^4=1' for b in blocks)
    assert any(b['kind'] == 'table' and b['cells'][-1] == ['幂', '4'] for b in blocks)
    assert any(b['kind'] == 'code' and '<script>' in b['text'] for b in blocks)
    assert not any(b.get('image', '').startswith('http') for b in blocks)
    assert result['warnings']


def test_docx_extracts_heading_table_and_embedded_image_without_office():
    result = parse(docx_bytes(), '课本.docx')
    assert result['blocks'][0]['text'] == '第一章 正数和负数'
    assert result['blocks'][0]['kind'] == 'heading'
    assert any(b.get('cells') == [['温度', '-3℃']] for b in result['blocks'])
    assert any(b.get('image', '').startswith('data:image/png;base64,') for b in result['blocks'])
    assert any(b['kind'] == 'unsupported' for b in result['blocks'])
    assert result['warnings']


def test_pptx_obeys_presentation_order_and_uses_slide_numbers():
    blocks = parse(pptx_bytes(), '课程.pptx')['blocks']
    assert blocks[0]['slide'] == 1 and blocks[0]['text'] == '认识分数'
    assert any(b['slide'] == 2 and '平均分' in b['text'] for b in blocks)
    assert all('page_number' not in b for b in blocks)


def test_chinese_encoding_requires_explicit_choice_and_never_replacement():
    data = '第一章\n负数小于零'.encode('gb18030')
    with pytest.raises(ValueError, match='编码'):
        parse(data, '课本.txt')
    assert parse(data, '课本.txt', encoding='gb18030')['blocks'][0]['text'] == '第一章'
    assert parse('正文'.encode('utf-16'), '课本.txt')['blocks'][0]['text'] == '正文'


@pytest.mark.parametrize('files', [
    {'../escape.xml': 'bad'},
    {'word/document.xml': '<!DOCTYPE x [<!ENTITY x "bad">]><x>&x;</x>'},
    {'word/vbaProject.bin': b'bad', 'word/document.xml': '<x/>'},
    {'word/document.xml': '<x/>', 'bomb': b'0' * (65 * 1024 * 1024)},
])
def test_unsafe_office_archives_are_rejected(files):
    with pytest.raises(ValueError):
        parse(package(files), 'bad.docx')


def test_remote_office_images_are_not_loaded():
    data = package({'word/document.xml': f'<w:document xmlns:w="{W}" xmlns:a="{A}" xmlns:r="{R}"><w:body><w:p><w:r><w:drawing><a:blip r:link="r1"/></w:drawing></w:r></w:p></w:body></w:document>',
                    'word/_rels/document.xml.rels': f'<Relationships xmlns="{REL}"><Relationship Id="r1" Target="https://evil.example/pixel" TargetMode="External" Type="{R}/image"/></Relationships>'})
    result = parse(data, 'remote.docx')
    assert result['warnings']
    assert not any(b.get('image') for b in result['blocks'])


def test_large_text_keeps_tail_and_stable_block_ids():
    content = '\n\n'.join(f'第{i}段知识' for i in range(1200)).encode()
    result = parse(content, '长教材.txt')
    assert len(result['blocks']) == 1200
    assert result['blocks'][-1]['text'] == '第1199段知识'
    assert result == parse(content, '长教材.txt')


def test_binary_disguised_text_is_rejected():
    with pytest.raises(ValueError):
        parse(b'\x00\x01\x02MZ', 'file.txt')
