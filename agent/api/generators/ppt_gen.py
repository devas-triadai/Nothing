"""
AGRA Phase 2 — PPT Generator
Builds .pptx files from structured JSON slide data using python-pptx.
Applies ICG-style formatting (navy/gold color scheme).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

logger = logging.getLogger("agra.ppt_gen")

# ICG brand colours
_NAVY = RGBColor(0x0B, 0x10, 0x20)       # #0B1020
_DARK_BLUE = RGBColor(0x1E, 0x3A, 0x8A)  # #1E3A8A
_GOLD = RGBColor(0xD4, 0xA5, 0x37)       # #D4A537
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_LIGHT_GRAY = RGBColor(0xE0, 0xE0, 0xE0)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def _set_slide_bg(slide, color: RGBColor = _NAVY):
    """Set solid background colour on a slide."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_text_box(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    font_size: int = 18,
    color: RGBColor = _WHITE,
    bold: bool = False,
    alignment=PP_ALIGN.LEFT,
):
    """Add a positioned text box to a slide."""
    txBox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.alignment = alignment
    return txBox


def _build_title_slide(prs: Presentation, title: str, subtitle: str = ""):
    """Create the title slide (slide 1)."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout
    _set_slide_bg(slide, _DARK_BLUE)

    # Title
    _add_text_box(slide, 1.0, 2.0, 8.0, 1.5, title,
                  font_size=36, color=_WHITE, bold=True, alignment=PP_ALIGN.CENTER)

    # Subtitle/date
    if subtitle:
        _add_text_box(slide, 1.0, 3.8, 8.0, 1.0, subtitle,
                      font_size=18, color=_GOLD, alignment=PP_ALIGN.CENTER)

    # ICG footer
    _add_text_box(slide, 1.0, 6.0, 8.0, 0.5,
                  "Indian Coast Guard Headquarters, New Delhi | AGRA System",
                  font_size=10, color=_LIGHT_GRAY, alignment=PP_ALIGN.CENTER)


def _build_content_slide(
    prs: Presentation,
    title: str,
    bullets: List[str],
    notes: str = "",
):
    """Create a content slide with title and bullet points."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank layout
    _set_slide_bg(slide, _NAVY)

    # Title bar background
    from pptx.shapes.autoshape import Shape
    shape = slide.shapes.add_shape(
        1,  # Rectangle
        Inches(0), Inches(0), Inches(10), Inches(1.2)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _DARK_BLUE
    shape.line.fill.background()

    # Title text
    _add_text_box(slide, 0.5, 0.2, 9.0, 0.8, title,
                  font_size=28, color=_WHITE, bold=True)

    # Accent line
    accent = slide.shapes.add_shape(
        1, Inches(0.5), Inches(1.15), Inches(2.0), Inches(0.04)
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = _GOLD
    accent.line.fill.background()

    # Bullet points
    if bullets:
        txBox = slide.shapes.add_textbox(
            Inches(0.7), Inches(1.5), Inches(8.5), Inches(5.0)
        )
        tf = txBox.text_frame
        tf.word_wrap = True

        for i, bullet in enumerate(bullets):
            if i == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            p.text = f"•  {bullet}"
            p.font.size = Pt(16)
            p.font.color.rgb = _LIGHT_GRAY
            p.space_after = Pt(12)

    # Speaker notes
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def build_pptx(
    slides_data: List[Dict[str, Any]],
    output_path: str,
    title: str = "AGRA Presentation",
    template_path: Optional[str] = None,
) -> str:
    """
    Build a .pptx file from structured slide data.

    Args:
        slides_data: List of {"title": str, "bullets": [str], "notes": str}
        output_path: Where to save the .pptx file.
        title: Presentation title (used if first slide is title slide).
        template_path: Optional path to a .pptx template file.

    Returns:
        Path to the generated .pptx file.
    """
    # Load template or create blank
    if template_path and Path(template_path).exists():
        prs = Presentation(template_path)
    else:
        prs = Presentation()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)

    for i, slide_data in enumerate(slides_data):
        slide_title = slide_data.get("title", f"Slide {i + 1}")
        bullets = slide_data.get("bullets", [])
        notes = slide_data.get("notes", "")

        if i == 0:
            # Title slide
            subtitle = bullets[0] if bullets else ""
            _build_title_slide(prs, slide_title, subtitle)
        else:
            _build_content_slide(prs, slide_title, bullets, notes)

    prs.save(output_path)
    logger.info("PPTX saved: %s (%d slides)", output_path, len(slides_data))
    return output_path
