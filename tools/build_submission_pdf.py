"""将本作业Markdown排成PDF；维护工具依赖reportlab，不影响银行程序。

使用Codex自带文档Python运行时；只读取Markdown，不执行文档中的代码。
"""

from __future__ import annotations

import argparse
import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def inline(text: str) -> str:
    """先转义尖括号，避免把ES高亮标签当成PDF排版标签。"""
    text = escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r'<font color="#23587a">\1</font>', text)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)


def build_pdf(source: Path, destination: Path) -> None:
    """保留源文档与既有PDF，输出一个新的PDF。"""
    if destination.exists():
        raise FileExistsError(f"保留既有PDF，请指定新输出路径：{destination}")
    pdfmetrics.registerFont(TTFont("YaHei", "C:/Windows/Fonts/msyh.ttc"))
    pdfmetrics.registerFont(TTFont("YaHeiBold", "C:/Windows/Fonts/msyhbd.ttc"))
    pdfmetrics.registerFontFamily("YaHei", normal="YaHei", bold="YaHeiBold")
    body = ParagraphStyle(
        "BankBody", fontName="YaHei", fontSize=9.5, leading=15,
        wordWrap="CJK", spaceAfter=5, textColor=colors.HexColor("#203244"),
    )
    code = ParagraphStyle(
        "BankCode", parent=body, fontSize=8, leading=12,
        spaceAfter=1, backColor=colors.HexColor("#f1f5f8"),
        leftIndent=7, rightIndent=7, borderPadding=4,
    )
    cell = ParagraphStyle("BankCell", parent=body, fontSize=8, leading=12, spaceAfter=0)
    headings = {
        level: ParagraphStyle(
            f"BankH{level}", parent=body, fontName="YaHeiBold",
            fontSize={1: 20, 2: 14, 3: 11}.get(level, 10),
            leading={1: 28, 2: 21, 3: 18}.get(level, 16),
            spaceBefore=10, spaceAfter=7, keepWithNext=True,
            textColor=colors.HexColor("#15496c"),
        )
        for level in range(1, 5)
    }
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    flow = []
    code_mode = False
    index = 0
    width = A4[0] - 84
    while index < len(lines):
        line = lines[index]
        index += 1
        if line.startswith("```"):
            code_mode = not code_mode
            flow.append(Spacer(1, 7))
            continue
        if code_mode:
            leading = len(line) - len(line.lstrip())
            content = "&#160;" * leading + escape(line.lstrip(), quote=False)
            flow.append(Paragraph(content or "&#160;", code))
            continue
        if not line.strip():
            continue
        if line.startswith("|"):
            table_lines = [line]
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            rows = []
            for row in table_lines:
                parts = [part.strip() for part in row.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-+:?", part) for part in parts):
                    continue
                rows.append([Paragraph(inline(part), cell) for part in parts])
            columns = max(len(row) for row in rows)
            table = Table(rows, colWidths=[width / columns] * columns, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dceaf3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c4d2dd")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            flow.extend([table, Spacer(1, 9)])
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)", line)
        if heading:
            flow.append(Paragraph(inline(heading[2]), headings[len(heading[1])]))
            continue
        if line.startswith("> "):
            line = line[2:]
        elif line.startswith("- "):
            line = "• " + line[2:]
        flow.append(Paragraph(inline(line), body))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("YaHei", 8)
        canvas.setFillColor(colors.HexColor("#657786"))
        canvas.drawString(42, 22, "Day37 银行智能问答系统 | 教学参考")
        canvas.drawRightString(A4[0] - 42, 22, str(document.page))
        canvas.restoreState()

    destination.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=42, leftMargin=42,
        topMargin=34, bottomMargin=38,
        title="Day37 银行智能问答系统作业", author="课程作业参考",
    )
    document.build(flow, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF_CREATED {destination.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    build_pdf(arguments.source, arguments.destination)



