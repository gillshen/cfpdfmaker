import os
import re
import jinja2
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TemplateRenderingError(RuntimeError):
    pass


class LuaLaTeXRuntimeError(RuntimeError):
    pass


def make_template(source_path):
    env = jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True
    )
    with open(source_path, encoding='utf-8') as template_file:
        return env.from_string(template_file.read())


def txt2tex(template: jinja2.Template,
            source_path: str,
            params: dict,
            target_path=None) -> None:
    """
    take a file path (pointing to a plain text file)
    parse its content, the result being a list of tuples (blocks)
    render a latex-ready str using the blocks and additional params
    and then write the str into the target file
    """
    with open(source_path, encoding='utf-8') as source:
        blocks = list(parse_txt(source.read()))

    try:
        tex_string = template.render(blocks=blocks, **params)
    except Exception as e:
        raise TemplateRenderingError(source_path) from e

    if not target_path:
        target_name = swap_ext(source_path, 'tex')
        target_path = os.path.join(ROOT, target_name)
    with open(target_path, 'w', encoding='utf-8') as target:
        target.write(tex_string)


def tex2pdf(source_path: str) -> None:
    print(source_path)
    args = [
        'lualatex',
        '--interaction=nonstopmode',
        source_path,
    ]
    try:
        subprocess.run(args, shell=False, check=True)
    except Exception as e:
        raise LuaLaTeXRuntimeError(source_path) from e


def parse_txt(s: str):
    """return a list of tuples (block_style, block_text)"""
    # replace soft linebreaks
    s = re.sub(r'(\\{2}|\\par )[ ]*\r?\n', r' \1 ', s)

    # split into blocks that do not contain newlines
    stripped_lines = (line.strip() for line in s.splitlines())

    for block in filter(None, stripped_lines):
        # detect the style of the block by the presence of starting `#`s
        *style_match, p = re.split(r'^(#+)', block)

        # if three or more `*`s on a line by themselves
        # it's a separator; no further action needed
        if re.match(r'^\s*\*+$', p):
            yield 'separator', ''
            continue

        # TODO more processing
        # convert \par to a proper line break
        # p = re.sub(r'\s*\\par\s+', '\n\n', p)

        # escape spcial characters
        p = re.sub(r'([&#%$])', r'\\\1', p)

        # process annotations
        p = re.sub(r'~~((?:[^~]|~[^~])+)~~', r'\\ntext{\1}', p)
        p = re.sub(r' *<<((?:[^>]|>[^>])+)>> *', r'\\note{\1} ', p)

        # process hyperlinks
        p = re.sub(r'\[([^]]+)\]\(([^)]+)\)', r'\\href{\2}{\1}', p)

        # process bold and italic text
        p = re.sub(r'\*\*((?:[^*]|\*[^*])+)\*\*', r'\\textbf{\1}', p)
        p = re.sub(r'\*([^*]+)\*', r'\\emph{\1}', p)
        # another pass to deal with nested cases
        p = re.sub(r'\*\*((?:[^*]|\*[^*])+)\*\*', r'\\textbf{\1}', p)

        # convert straight quotes to tex-style quotation marks
        p = re.sub(r'(\s|\(|\{|^)"', r'\1``', p)
        p = re.sub(r"(\s|\(|\{|^)'", r'\1`', p)
        p = p.replace('"', "''")

        # use paddable dashes
        p = re.sub(r'\s*(?:---|—)\s*|\s+(?:-|–)\s+', r'\\mdash ', p)
        p = re.sub(r'\s*--\s*', r'\\ndash ', p)

        # use custom ellipsis
        p = re.sub(r'\s*(\.\.\.|…)\s*', r'\\ellipsis ', p)

        # consolidate whitespace
        p = re.sub(r'\s+', ' ', p).strip()

        if not style_match:
            style = 'body'
        else:
            style_code = len(style_match[1])
            if style_code == 1:
                style = 'prompt'
            elif style_code == 2:
                style = 'title'
            else:
                style = 'addendum'
        yield style, p


def swap_ext(source_name: str, ext: str, base_only=False) -> str:
    if base_only:
        source_name = os.path.basename(source_name)
    root, _ = os.path.splitext(source_name)
    return f'{root}.{ext}'


def delete_helper_files(tex_path):
    for ext in ['aux', 'log', 'out', 'synctex.gz']:
        try:
            os.remove(swap_ext(tex_path, ext))
        except FileNotFoundError:
            pass


if __name__ == '__main__':
    with open('src/test.txt', encoding='utf-8') as f:
        blocks = parse_txt(f.read())
    for (style, text) in blocks:
        print(f'\nBEGIN BLOCK {style}')
        print(text)
        print('END BLOCK\n')
