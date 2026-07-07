"""
PDF generation utilities for Summary and Quiz exports.
Uses fpdf2 (pure Python, no system dependencies).
"""
import logging
from pathlib import Path
from typing import List, Optional

from fpdf import FPDF

logger = logging.getLogger("agra.pdf_gen")


class PDFGenerator(FPDF):
    """Custom PDF generator with header/footer for ICG AGRA documents."""

    def header(self):
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 6, "Indian Coast Guard - AGRA", align="L")
        self.cell(0, 6, "AI-Generated Draft", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def add_title_page(self, title: str, subtitle: Optional[str] = None):
        self.add_page()
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(20, 60, 120)
        self.ln(40)
        self.multi_cell(0, 12, title, align="C")
        if subtitle:
            self.ln(6)
            self.set_font("Helvetica", "", 13)
            self.set_text_color(80, 80, 80)
            self.multi_cell(0, 8, subtitle, align="C")

    def add_heading(self, text: str, level: int = 1):
        sizes = {1: 16, 2: 13, 3: 11}
        styles = {1: "B", 2: "B", 3: ""}
        size = sizes.get(level, 11)
        style = styles.get(level, "")
        self.ln(4)
        self.set_font("Helvetica", style, size)
        self.set_text_color(20, 60, 120)
        self.multi_cell(0, 8, text)
        self.ln(2)

    def add_paragraph(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def add_bullet(self, text: str, indent: int = 10):
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        bullet_char = "\u2022"
        self.cell(5, 5.5, bullet_char)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def add_warning_box(self, text: str):
        self.set_fill_color(255, 243, 205)
        self.set_text_color(133, 100, 4)
        self.set_font("Helvetica", "B", 10)
        self.set_x(15)
        self.multi_cell(0, 6, text, fill=True)
        self.ln(3)


def generate_summary_pdf(
    title: str,
    content_text: str,
    output_path: Path,
    detail_level: str = "detailed",
) -> str:
    """Generate a PDF for a summary document."""
    pdf = PDFGenerator()
    pdf.alias_nb_pages()
    pdf.add_title_page(title, f"Summary ({detail_level.title()})")

    # Split content into lines and render
    lines = content_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            pdf.ln(2)
        elif line.startswith("# ") or line.startswith("**"):
            pdf.add_heading(line.lstrip("# *").rstrip("*"), level=1)
        elif line.startswith("## ") or line.startswith("**") and "**" in line[2:]:
            pdf.add_heading(line.lstrip("# *").rstrip("*"), level=2)
        elif line.startswith("- ") or line.startswith("* "):
            pdf.add_bullet(line[2:])
        else:
            pdf.add_paragraph(line)

    pdf.output(str(output_path))
    return output_path.name


def generate_quiz_pdf(
    quiz_data: dict,
    filename: str,
    output_path: Path,
    user_answers: Optional[dict] = None,
    score: Optional[dict] = None,
) -> str:
    """Generate a PDF for a quiz, optionally including user answers and score."""
    pdf = PDFGenerator()
    pdf.alias_nb_pages()
    title = quiz_data.get("title", "Knowledge Quiz")
    pdf.add_title_page(title)

    if score:
        pdf.add_warning_box(
            f"Score: {score.get('correct', 0)}/{score.get('total', 0)} "
            f"({score.get('percentage', 0):.0f}%)"
        )

    mcqs = quiz_data.get("mcq", [])
    if mcqs:
        pdf.add_heading("Multiple Choice Questions", level=1)
        for i, q in enumerate(mcqs, 1):
            pdf.add_paragraph(f"Q{i}. {q.get('question', '')}")
            options = q.get("options", {})
            for key in ("A", "B", "C", "D"):
                opt = options.get(key, "")
                correct = q.get("correct", "")
                is_correct = key == correct
                marker = "  [CORRECT]" if is_correct else ""
                user_mark = ""
                if user_answers:
                    ua = user_answers.get(f"mcq_{i-1}")
                    if ua == key:
                        user_mark = "  [YOUR ANSWER]" if not is_correct else "  [YOUR ANSWER]"
                pdf.add_bullet(f"{key}) {opt}{marker}{user_mark}")
            if q.get("explanation"):
                pdf.add_paragraph(f"Explanation: {q['explanation']}")
            pdf.ln(2)

    tfs = quiz_data.get("true_false", [])
    if tfs:
        pdf.add_heading("True / False Questions", level=1)
        for i, q in enumerate(tfs, 1):
            ans = "True" if q.get("answer") is True else "False"
            pdf.add_paragraph(f"T/F {i}. {q.get('question', '')}")
            pdf.add_paragraph(f"  Answer: {ans}")
            if user_answers:
                ua = user_answers.get(f"tf_{i-1}")
                if ua is not None:
                    pdf.add_paragraph(f"  Your Answer: {'True' if ua else 'False'}")
            if q.get("explanation"):
                pdf.add_paragraph(f"Explanation: {q['explanation']}")
            pdf.ln(2)

    sas = quiz_data.get("short_answer", [])
    if sas:
        pdf.add_heading("Short Answer Questions", level=1)
        for i, q in enumerate(sas, 1):
            pdf.add_paragraph(f"SA{i}. {q.get('question', '')}")
            pdf.add_paragraph(f"Model Answer: {q.get('model_answer', '')}")
            if user_answers and f"sa_{i-1}" in user_answers:
                pdf.add_paragraph(f"Your Answer: {user_answers[f'sa_{i-1}']}")
            pdf.ln(2)

    pdf.output(str(output_path))
    return output_path.name
