#!/usr/bin/env python3
"""
code_to_pdf.py — Convert a source code file to a syntax-highlighted PDF.

Usage:
    python code_to_pdf.py <input_file> [output.pdf]

Dependencies:
    pip install reportlab pygments --break-system-packages
"""

import sys
import os
import argparse
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import Table, TableStyle
from reportlab.pdfgen import canvas
from pygments import highlight
from pygments.lexers import get_lexer_for_filename, get_lexer_by_name, TextLexer
from pygments.token import Token


# ── Colour theme (VS Code Dark+ inspired) ──────────────────────────────────
THEME = {
    "bg":           colors.HexColor("#1e1e1e"),
    "fg":           colors.HexColor("#d4d4d4"),
    "line_num_bg":  colors.HexColor("#2d2d2d"),
    "line_num_fg":  colors.HexColor("#858585"),
    "header_bg":    colors.HexColor("#007acc"),
    "header_fg":    colors.white,
    # Syntax token colours
    Token.Keyword:              colors.HexColor("#569cd6"),
    Token.Keyword.Declaration:  colors.HexColor("#569cd6"),
    Token.Keyword.Namespace:    colors.HexColor("#c586c0"),
    Token.Keyword.Type:         colors.HexColor("#4ec9b0"),
    Token.Name.Builtin:         colors.HexColor("#dcdcaa"),
    Token.Name.Function:        colors.HexColor("#dcdcaa"),
    Token.Name.Class:           colors.HexColor("#4ec9b0"),
    Token.Name.Decorator:       colors.HexColor("#c586c0"),
    Token.Literal.String:       colors.HexColor("#ce9178"),
    Token.Literal.String.Doc:   colors.HexColor("#6a9955"),
    Token.Literal.Number:       colors.HexColor("#b5cea8"),
    Token.Comment:              colors.HexColor("#6a9955"),
    Token.Comment.Single:       colors.HexColor("#6a9955"),
    Token.Comment.Multiline:    colors.HexColor("#6a9955"),
    Token.Operator:             colors.HexColor("#d4d4d4"),
    Token.Punctuation:          colors.HexColor("#d4d4d4"),
    Token.Name:                 colors.HexColor("#9cdcfe"),
    Token.Name.Attribute:       colors.HexColor("#9cdcfe"),
}

CODE_FONT  = "Courier"
CODE_SIZE  = 8
LINE_H     = CODE_SIZE * 1.35   # pt


def token_color(ttype):
    """Walk up the token hierarchy until we find a matching colour."""
    while ttype:
        if ttype in THEME:
            return THEME[ttype]
        ttype = ttype.parent
    return THEME["fg"]


def to_hex(color) -> str:
    """Return a 6-digit hex string (no #) for any ReportLab color."""
    try:
        r, g, b = color.red, color.green, color.blue
        return f"{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    except Exception:
        return "d4d4d4"


def xml_escape(text):
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


class NumberedCanvas(canvas.Canvas):
    """Canvas that stamps page numbers at the bottom of every page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_page_number(self, total):
        w, h = self._pagesize
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#888888"))
        self.drawCentredString(w / 2, 8 * mm, f"Page {self._pageNumber} of {total}")


def build_pdf(input_path: str, output_path: str):
    # ── Read source ──────────────────────────────────────────────────────────
    with open(input_path, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()

    filename = os.path.basename(input_path)

    # ── Choose lexer ─────────────────────────────────────────────────────────
    try:
        lexer = get_lexer_for_filename(filename)
    except Exception:
        try:
            lexer = get_lexer_by_name("text")
        except Exception:
            lexer = TextLexer()

    language = lexer.name

    # ── Tokenise ─────────────────────────────────────────────────────────────
    tokens = list(lexer.get_tokens(source))

    # Build list of (line_number, [(text, colour), ...])
    lines = []
    current_line = []
    lineno = 1
    for ttype, value in tokens:
        col = token_color(ttype)
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if part:
                current_line.append((part, col))
            if i < len(parts) - 1:          # newline boundary
                lines.append((lineno, current_line))
                current_line = []
                lineno += 1
    if current_line:
        lines.append((lineno, current_line))

    # ── Page layout ──────────────────────────────────────────────────────────
    PAGE      = A4
    PW, PH    = PAGE
    MARGIN    = 15 * mm
    LN_W      = 28               # pt — line-number column width
    CODE_X    = MARGIN + LN_W + 4
    CODE_W    = PW - MARGIN - CODE_X - MARGIN

    doc = SimpleDocTemplate(
        output_path,
        pagesize=PAGE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=18 * mm,
        title=filename,
        author="code_to_pdf.py",
    )

    # ── Header style ─────────────────────────────────────────────────────────
    header_style = ParagraphStyle(
        "header",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=THEME["header_fg"],
        backColor=THEME["header_bg"],
        leftIndent=6,
        spaceBefore=0,
        spaceAfter=4,
        leading=18,
    )
    meta_style = ParagraphStyle(
        "meta",
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#aaaaaa"),
        spaceAfter=6,
        leading=12,
    )

    story = []

    # Title / header block
    story.append(Paragraph(f"&#128196; {xml_escape(filename)}", header_style))
    story.append(Paragraph(
        f"Language: <b>{xml_escape(language)}</b> &nbsp;|&nbsp; "
        f"Lines: <b>{len(lines)}</b> &nbsp;|&nbsp; "
        f"Size: <b>{os.path.getsize(input_path):,} bytes</b>",
        meta_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=THEME["header_bg"], spaceAfter=4))

    # ── Render code as a ReportLab Table ─────────────────────────────────────
    # Each row = [line_number_cell, code_cell]
    # We build the code cell as a hand-crafted multi-colour string using
    # ReportLab's Paragraph XML markup.

    row_data = []
    row_styles = []

    for idx, (lnum, spans) in enumerate(lines):
        # Line-number cell
        ln_para = Paragraph(
            f'<font color="#{to_hex(THEME["line_num_fg"])}">{lnum}</font>',
            ParagraphStyle(
                "ln",
                fontName=CODE_FONT,
                fontSize=CODE_SIZE,
                leading=LINE_H,
                alignment=TA_LEFT,
                textColor=THEME["line_num_fg"],
            ),
        )

        # Code cell — build coloured XML
        xml_parts = []
        for text, col in spans:
            hex_col = f"#{to_hex(col)}"
            xml_parts.append(f'<font color="{hex_col}">{xml_escape(text)}</font>')
        code_xml = "".join(xml_parts) or " "

        code_para = Paragraph(
            code_xml,
            ParagraphStyle(
                "code",
                fontName=CODE_FONT,
                fontSize=CODE_SIZE,
                leading=LINE_H,
                textColor=THEME["fg"],
                wordWrap="LTR",
            ),
        )

        row_data.append([ln_para, code_para])

        # Alternate-row background for readability
        bg = THEME["bg"] if idx % 2 == 0 else colors.HexColor("#252526")
        row_styles += [
            ("BACKGROUND", (0, idx), (-1, idx), bg),
            ("BACKGROUND", (0, idx), (0, idx), THEME["line_num_bg"]),
        ]

    col_widths = [LN_W, CODE_W]

    table = Table(row_data, colWidths=col_widths, repeatRows=0)
    table.setStyle(TableStyle([
        ("FONTNAME",    (0, 0), (-1, -1), CODE_FONT),
        ("FONTSIZE",    (0, 0), (-1, -1), CODE_SIZE),
        ("LEADING",     (0, 0), (-1, -1), LINE_H),
        ("TOPPADDING",  (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (0, -1),  3),
        ("RIGHTPADDING", (0, 0), (0, -1), 3),
        ("LEFTPADDING", (1, 0), (1, -1),  4),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("ALIGN",       (0, 0), (0, -1),  "RIGHT"),
        ("BACKGROUND",  (0, 0), (-1, -1), THEME["bg"]),
        *row_styles,
    ]))

    story.append(table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅  Saved → {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Convert a code file to a syntax-highlighted PDF.")
    parser.add_argument("input",  help="Path to the source code file")
    parser.add_argument("output", nargs="?", help="Output PDF path (default: <input>.pdf)")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    output = args.output or os.path.splitext(args.input)[0] + ".pdf"
    build_pdf(args.input, output)


if __name__ == "__main__":
    main()