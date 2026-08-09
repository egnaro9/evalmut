#!/usr/bin/env python3
"""Render paper/evalmut.md to a clean academic HTML (paper/evalmut.html) for Chrome print-to-PDF.
Focused Markdown subset: #/## headers, **bold**, *italic*, `code`, fenced ``` blocks, - lists,
[text](url) links, > blockquote, paragraphs. No external deps."""
import html
import re
import sys
from pathlib import Path

SRC = Path(__file__).parent / "evalmut.md"
OUT = Path(__file__).parent / "evalmut.html"


def inline(text: str) -> str:
    # protect inline code, then escape, then apply emphasis/links, then restore code.
    codes = []
    def stash(m):
        codes.append(m.group(1))
        return f"\0{len(codes)-1}\0"
    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\0(\d+)\0", lambda m: "<code>" + html.escape(codes[int(m.group(1))]) + "</code>", text)
    return text


def convert(md: str) -> str:
    out, i = [], 0
    lines = md.split("\n")
    para: list[str] = []
    list_open = False

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para = []

    def close_list():
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):                       # fenced code block
            flush_para(); close_list()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            i += 1
            continue
        if not line.strip():                              # blank -> break para/list
            flush_para(); close_list(); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para(); close_list()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1; continue
        if line.startswith("> "):                         # blockquote (single-para)
            flush_para(); close_list()
            out.append("<blockquote>" + inline(line[2:]) + "</blockquote>")
            i += 1; continue
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            flush_para()
            if not list_open:
                out.append("<ul>"); list_open = True
            item = m.group(1)
            i += 1                                        # gather continuation lines of the item
            while i < len(lines) and lines[i].strip() and not re.match(r"^[-*#>]|^```", lines[i]):
                item += " " + lines[i].strip(); i += 1
            out.append("<li>" + inline(item) + "</li>")
            continue
        para.append(line.strip()); i += 1

    flush_para(); close_list()
    return "\n".join(out)


CSS = """
@page { size: letter; margin: 0.9in 0.95in; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.5 "Palatino Linotype","Palatino","Book Antiqua",Georgia,serif;
       color:#111; max-width:100%; margin:0; text-align:justify; hyphens:auto; }
h1 { font-size:17pt; text-align:center; margin:0 0 .1em; line-height:1.25; }
h1 + p { text-align:center; color:#333; font-size:9.5pt; margin:0 0 1.4em; }
h2 { font-size:12.5pt; margin:1.5em 0 .4em; border-bottom:0.6pt solid #bbb; padding-bottom:2pt; }
h3 { font-size:11pt; margin:1.1em 0 .3em; }
p, li { orphans:2; widows:2; }
ul { margin:.4em 0 .6em 1.1em; padding:0; }
li { margin:.25em 0; text-align:left; }
a { color:#1a3e6e; text-decoration:none; }
code { font-family:"SF Mono",Menlo,Consolas,monospace; font-size:8.8pt; background:#f3f3f3;
       padding:0 2px; border-radius:2px; }
pre { background:#f6f6f6; border:0.5pt solid #ddd; border-radius:3px; padding:7pt 9pt;
      overflow-x:auto; page-break-inside:avoid; margin:.6em 0; }
pre code { background:none; padding:0; font-size:8.2pt; line-height:1.35; white-space:pre-wrap; }
blockquote { margin:.7em 0; padding:.2em 0 .2em 12pt; border-left:2.5pt solid #888;
             color:#222; font-style:italic; }
strong { font-weight:700; }
h2:first-of-type { page-break-before:avoid; }
"""

md = SRC.read_text(encoding="utf-8")
body = convert(md)
doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>evalmut — Mutation Testing for LLM Eval Graders</title><style>{CSS}</style></head>
<body>{body}</body></html>"""
OUT.write_text(doc, encoding="utf-8")
print(f"wrote {OUT} ({len(doc)} bytes)")
