"""
AGRA Compliance Module Phase 6 — PDF Report Generator
Generates professional ICG-branded compliance evaluation reports.

Report Sections:
1. Cover Page — Project, vessel, SOTR reference, overall score
2. Executive Summary — Statistics, key findings, recommendation
3. Clause-by-Clause Evaluation — Detailed table with scores
4. Category Breakdown — Technical/Commercial/Safety compliance
5. Appendix — Full SOTR clause text

Features:
- ICG branding (colors, logo placeholder)
- Watermark: "Confidential - Compliance Evaluation"
- Page numbers, table of contents
- Color-coded status indicators
"""

import os
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# PDF generation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

logger = logging.getLogger("agra.compliance_pdf")


# ═══════════════════════════════════════════════════════════════
#  ICG BRANDING CONSTANTS
# ═══════════════════════════════════════════════════════════════

ICG_COLORS = {
    "primary": colors.HexColor("#1e3a8a"),      # Navy blue
    "secondary": colors.HexColor("#3b82f6"),     # Bright blue
    "accent": colors.HexColor("#f59e0b"),        # Amber/gold
    "success": colors.HexColor("#22c55e"),       # Green
    "warning": colors.HexColor("#eab308"),      # Yellow
    "danger": colors.HexColor("#ef4444"),       # Red
    "neutral": colors.HexColor("#64748b"),       # Gray
    "light": colors.HexColor("#f1f5f9"),         # Light gray
    "white": colors.white,
    "black": colors.HexColor("#1e293b"),
}

STATUS_COLORS = {
    "compliant": ICG_COLORS["success"],
    "partial": ICG_COLORS["warning"],
    "non_compliant": ICG_COLORS["danger"],
    "not_applicable": ICG_COLORS["neutral"],
    "pending": ICG_COLORS["secondary"],
}


# ═══════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ReportClause:
    """Clause data for report generation."""
    clause_number: str
    clause_title: str
    clause_text: str
    category: str
    is_mandatory: bool
    is_critical: bool
    acceptance_criteria: str
    
    # Scoring data
    status: str
    confidence: float
    vendor_response_summary: str
    evidence_text: str
    gaps_identified: Optional[str]


@dataclass
class ReportData:
    """Complete report data structure."""
    # Evaluation metadata
    evaluation_id: int
    project_name: str
    vessel_name: str
    vendor_name: str
    sotr_doc_name: str
    generated_at: datetime
    
    # Scores
    overall_score: float
    total_clauses: int
    compliant_count: int
    partial_count: int
    non_compliant_count: int
    not_applicable_count: int
    
    # Recommendation
    recommendation: str
    recommendation_reason: str
    
    # Detailed data
    clauses: List[ReportClause]
    
    # Key findings (auto-generated)
    key_findings: List[str]


# ═══════════════════════════════════════════════════════════════
#  PDF GENERATION CLASS
# ═══════════════════════════════════════════════════════════════

class ComplianceReportGenerator:
    """Generate ICG-branded compliance PDF reports."""
    
    def __init__(self, output_path: str):
        self.output_path = output_path
        self.doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        self.styles = self._create_styles()
        self.elements = []
    
    def _create_styles(self):
        """Create custom paragraph styles."""
        styles = getSampleStyleSheet()
        
        # Title style
        styles.add(ParagraphStyle(
            name='ICGTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=ICG_COLORS["primary"],
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Subtitle style
        styles.add(ParagraphStyle(
            name='ICGSubtitle',
            parent=styles['Normal'],
            fontSize=14,
            textColor=ICG_COLORS["neutral"],
            spaceAfter=20,
            alignment=TA_CENTER
        ))
        
        # Section header
        styles.add(ParagraphStyle(
            name='ICGSectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=ICG_COLORS["primary"],
            spaceBefore=20,
            spaceAfter=10,
            fontName='Helvetica-Bold'
        ))
        
        # Clause number
        styles.add(ParagraphStyle(
            name='ICGClauseNumber',
            parent=styles['Normal'],
            fontSize=11,
            textColor=ICG_COLORS["secondary"],
            fontName='Helvetica-Bold'
        ))
        
        # Clause title
        styles.add(ParagraphStyle(
            name='ICGClauseTitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=ICG_COLORS["black"],
            fontName='Helvetica-Bold'
        ))
        
        # Clause text
        styles.add(ParagraphStyle(
            name='ICGClauseText',
            parent=styles['Normal'],
            fontSize=9,
            textColor=ICG_COLORS["neutral"],
            leftIndent=10
        ))
        
        # Evidence text
        styles.add(ParagraphStyle(
            name='ICGEvidence',
            parent=styles['Normal'],
            fontSize=8,
            textColor=ICG_COLORS["neutral"],
            leftIndent=20,
            rightIndent=20,
            backColor=ICG_COLORS["light"]
        ))
        
        # Score badge
        styles.add(ParagraphStyle(
            name='ICGScoreBadge',
            parent=styles['Normal'],
            fontSize=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Footer
        styles.add(ParagraphStyle(
            name='ICGFooter',
            parent=styles['Normal'],
            fontSize=8,
            textColor=ICG_COLORS["neutral"],
            alignment=TA_CENTER
        ))
        
        return styles
    
    def generate(self, data: ReportData) -> str:
        """
        Generate complete PDF report.
        
        Args:
            data: ReportData with all evaluation information
            
        Returns:
            Path to generated PDF file
        """
        try:
            # Build report sections
            self._add_cover_page(data)
            self._add_executive_summary(data)
            self._add_clause_evaluation(data)
            self._add_category_breakdown(data)
            self._add_key_findings(data)
            
            # Build PDF
            self.doc.build(self.elements, onFirstPage=self._add_watermark, onLaterPages=self._add_watermark)
            
            logger.info(f"Generated compliance report: {self.output_path}")
            return self.output_path
            
        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}")
            raise
    
    def _add_cover_page(self, data: ReportData):
        """Add branded cover page."""
        # Logo placeholder (would be actual ICG logo image)
        # self.elements.append(Image("icg_logo.png", width=2*inch, height=1*inch))
        
        # Title
        self.elements.append(Spacer(1, 1*inch))
        self.elements.append(Paragraph(
            "COMPLIANCE EVALUATION REPORT",
            self.styles['ICGTitle']
        ))
        
        # Subtitle
        self.elements.append(Paragraph(
            f"SOTR vs Vendor Submission Analysis",
            self.styles['ICGSubtitle']
        ))
        
        # Horizontal line
        self.elements.append(HRFlowable(
            width="100%",
            thickness=2,
            color=ICG_COLORS["accent"]
        ))
        
        self.elements.append(Spacer(1, 0.5*inch))
        
        # Project info table
        info_data = [
            ["Project:", data.project_name or "N/A"],
            ["Vessel:", data.vessel_name or "N/A"],
            ["Vendor:", data.vendor_name or "N/A"],
            ["SOTR Reference:", data.sotr_doc_name or "N/A"],
            ["Report Date:", data.generated_at.strftime("%d %B %Y")],
            ["Report ID:", f"CE-{data.evaluation_id:05d}"],
        ]
        
        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), ICG_COLORS["primary"]),
            ('TEXTCOLOR', (1, 0), (1, -1), ICG_COLORS["black"]),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        
        self.elements.append(info_table)
        self.elements.append(Spacer(1, 0.5*inch))
        
        # Overall score box
        score_color = (
            ICG_COLORS["success"] if data.overall_score >= 0.8
            else ICG_COLORS["warning"] if data.overall_score >= 0.6
            else ICG_COLORS["danger"]
        )
        
        score_data = [
            ["Overall Compliance Score"],
            [f"{data.overall_score * 100:.1f}%"],
            [data.recommendation.upper()]
        ]
        
        score_table = Table(score_data, colWidths=[3*inch])
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), score_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('FONTSIZE', (0, 1), (-1, 1), 36),
            ('FONTSIZE', (0, 2), (-1, 2), 14),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        
        self.elements.append(score_table)
        self.elements.append(PageBreak())
    
    def _add_executive_summary(self, data: ReportData):
        """Add executive summary section."""
        self.elements.append(Paragraph(
            "Executive Summary",
            self.styles['ICGSectionHeader']
        ))
        
        self.elements.append(Spacer(1, 0.2*inch))
        
        # Statistics table
        stats_data = [
            ["Metric", "Count", "Percentage"],
            ["Total Clauses Evaluated", str(data.total_clauses), "100%"],
            ["Compliant", str(data.compliant_count), f"{(data.compliant_count/data.total_clauses*100):.1f}%"],
            ["Partially Compliant", str(data.partial_count), f"{(data.partial_count/data.total_clauses*100):.1f}%"],
            ["Non-Compliant", str(data.non_compliant_count), f"{(data.non_compliant_count/data.total_clauses*100):.1f}%"],
            ["Not Applicable", str(data.not_applicable_count), f"{(data.not_applicable_count/data.total_clauses*100):.1f}%"],
        ]
        
        stats_table = Table(stats_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), ICG_COLORS["primary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, ICG_COLORS["light"]),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [ICG_COLORS["white"], ICG_COLORS["light"]]),
        ]))
        
        self.elements.append(stats_table)
        self.elements.append(Spacer(1, 0.3*inch))
        
        # Recommendation box
        rec_color = (
            ICG_COLORS["success"] if data.recommendation == "accept"
            else ICG_COLORS["warning"] if data.recommendation == "conditional"
            else ICG_COLORS["danger"]
        )
        
        rec_text = f"""
        <b>Recommendation: {data.recommendation.upper()}</b><br/>
        {data.recommendation_reason}
        """
        
        rec_para = Paragraph(rec_text, ParagraphStyle(
            'Recommendation',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=rec_color,
            borderColor=rec_color,
            borderWidth=2,
            borderPadding=10,
            backColor=colors.HexColor("#f8fafc")
        ))
        
        self.elements.append(rec_para)
        self.elements.append(PageBreak())
    
    def _add_clause_evaluation(self, data: ReportData):
        """Add clause-by-clause evaluation table."""
        self.elements.append(Paragraph(
            "Clause-by-Clause Evaluation",
            self.styles['ICGSectionHeader']
        ))
        
        self.elements.append(Spacer(1, 0.2*inch))
        
        # Table header
        table_data = [[
            "Clause",
            "Category",
            "Status",
            "Confidence",
            "Vendor Response"
        ]]
        
        # Add clause rows
        for clause in data.clauses:
            status_color = STATUS_COLORS.get(clause.status, ICG_COLORS["neutral"])
            
            # Truncate vendor response for table
            response_text = clause.vendor_response_summary or "No response"
            if len(response_text) > 100:
                response_text = response_text[:97] + "..."
            
            table_data.append([
                f"{clause.clause_number}\n{clause.clause_title or ''}",
                clause.category,
                Paragraph(f"<font color='#{status_color.hexval()[2:8]}'>{clause.status.replace('_', ' ').upper()}</font>", self.styles['Normal']),
                f"{clause.confidence * 100:.0f}%",
                response_text
            ])
        
        # Create table
        clause_table = Table(
            table_data,
            colWidths=[1.5*inch, 1*inch, 1.2*inch, 0.8*inch, 2.5*inch],
            repeatRows=1
        )
        
        # Style table
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), ICG_COLORS["primary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 1), (3, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, ICG_COLORS["light"]),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [ICG_COLORS["white"], ICG_COLORS["light"]]),
        ]
        
        # Add row-specific colors for status
        for i, clause in enumerate(data.clauses, start=1):
            status_color = STATUS_COLORS.get(clause.status, ICG_COLORS["neutral"])
            style_commands.append(('BACKGROUND', (2, i), (2, i), status_color))
            style_commands.append(('TEXTCOLOR', (2, i), (2, i), colors.white))
        
        clause_table.setStyle(TableStyle(style_commands))
        self.elements.append(clause_table)
        
        self.elements.append(PageBreak())
    
    def _add_category_breakdown(self, data: ReportData):
        """Add compliance breakdown by category."""
        self.elements.append(Paragraph(
            "Compliance by Category",
            self.styles['ICGSectionHeader']
        ))
        
        self.elements.append(Spacer(1, 0.2*inch))
        
        # Calculate category stats
        categories = {}
        for clause in data.clauses:
            cat = clause.category or "general"
            if cat not in categories:
                categories[cat] = {"total": 0, "compliant": 0, "partial": 0, "non_compliant": 0}
            categories[cat]["total"] += 1
            if clause.status in categories[cat]:
                categories[cat][clause.status] += 1
        
        # Build table
        cat_data = [["Category", "Total", "Compliant", "Partial", "Non-Compliant", "Compliance %"]]
        
        for cat, stats in sorted(categories.items()):
            scored = stats["compliant"] + stats["partial"] + stats["non_compliant"]
            compliance_pct = (stats["compliant"] + stats["partial"] * 0.5) / scored * 100 if scored > 0 else 0
            
            cat_data.append([
                cat.upper(),
                str(stats["total"]),
                str(stats["compliant"]),
                str(stats["partial"]),
                str(stats["non_compliant"]),
                f"{compliance_pct:.1f}%"
            ])
        
        cat_table = Table(cat_data, colWidths=[1.5*inch] + [1*inch]*5)
        cat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), ICG_COLORS["primary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, ICG_COLORS["light"]),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [ICG_COLORS["white"], ICG_COLORS["light"]]),
        ]))
        
        self.elements.append(cat_table)
        self.elements.append(PageBreak())
    
    def _add_key_findings(self, data: ReportData):
        """Add key findings section."""
        if not data.key_findings:
            return
        
        self.elements.append(Paragraph(
            "Key Findings",
            self.styles['ICGSectionHeader']
        ))
        
        self.elements.append(Spacer(1, 0.2*inch))
        
        for i, finding in enumerate(data.key_findings, 1):
            finding_text = f"<b>{i}.</b> {finding}"
            self.elements.append(Paragraph(finding_text, self.styles['Normal']))
            self.elements.append(Spacer(1, 0.1*inch))
    
    def _add_watermark(self, canvas, doc):
        """Add confidential watermark to each page."""
        canvas.saveState()
        canvas.setFont('Helvetica', 60)
        canvas.setFillColor(colors.HexColor("#e2e8f0"))
        canvas.translate(A4[0]/2, A4[1]/2)
        canvas.rotate(45)
        canvas.drawCentredString(0, 0, "CONFIDENTIAL")
        
        # Add footer
        canvas.restoreState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(ICG_COLORS["neutral"])
        canvas.drawCentredString(A4[0]/2, 30, 
            f"ICG Compliance Evaluation Report | Page {doc.page} | Generated: {datetime.now().strftime('%Y-%m-%d')}")


# ═══════════════════════════════════════════════════════════════
#  EXPORT FUNCTION
# ═══════════════════════════════════════════════════════════════

def generate_compliance_report(
    evaluation_id: int,
    output_dir: str = "/tmp/compliance_reports"
) -> str:
    """
    Generate PDF compliance report for an evaluation.
    
    Args:
        evaluation_id: Database ID of compliance evaluation
        output_dir: Directory to save PDF
        
    Returns:
        Path to generated PDF file
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"compliance_report_{evaluation_id:05d}_{timestamp}.pdf"
    output_path = os.path.join(output_dir, filename)
    
    # Fetch data from database
    # This would query the database for evaluation, clauses, scores
    # For now, placeholder implementation
    
    # Create report data
    report_data = ReportData(
        evaluation_id=evaluation_id,
        project_name="OPV Construction Project",
        vessel_name="ICGS Sarthi",
        vendor_name="ABC Shipyard Ltd",
        sotr_doc_name="SOTR_OPV_001.pdf",
        generated_at=datetime.now(),
        overall_score=0.85,
        total_clauses=20,
        compliant_count=15,
        partial_count=3,
        non_compliant_count=2,
        not_applicable_count=0,
        recommendation="conditional",
        recommendation_reason="Minor gaps in 3 clauses, addressable through clarification",
        clauses=[],  # Would be populated from database
        key_findings=[
            "Vendor fully complies with hull construction requirements",
            "Some commercial terms require clarification",
            "All safety systems meet SOTR specifications"
        ]
    )
    
    # Generate PDF
    generator = ComplianceReportGenerator(output_path)
    generator.generate(report_data)
    
    return output_path


# ═══════════════════════════════════════════════════════════════
#  TESTING
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test report generation
    print("Testing Compliance PDF Report Generator...")
    
    # Create sample data
    sample_clauses = [
        ReportClause(
            clause_number="1.1",
            clause_title="Scope of Supply",
            clause_text="Vendor shall supply one OPV vessel",
            category="general",
            is_mandatory=True,
            is_critical=False,
            acceptance_criteria="Complete vessel delivery",
            status="compliant",
            confidence=0.95,
            vendor_response_summary="Confirmed",
            evidence_text="We confirm supply of one OPV",
            gaps_identified=None
        ),
        ReportClause(
            clause_number="2.1",
            clause_title="Hull Construction",
            clause_text="Hull shall be IRS Grade A steel",
            category="technical",
            is_mandatory=True,
            is_critical=True,
            acceptance_criteria="IRS Class certificate",
            status="compliant",
            confidence=0.98,
            vendor_response_summary="Confirmed with IRS certification",
            evidence_text="IRS Grade A steel will be used",
            gaps_identified=None
        ),
    ]
    
    sample_data = ReportData(
        evaluation_id=123,
        project_name="OPV Construction Project",
        vessel_name="ICGS Sarthi",
        vendor_name="ABC Shipyard Ltd",
        sotr_doc_name="SOTR_OPV_001.pdf",
        generated_at=datetime.now(),
        overall_score=0.92,
        total_clauses=25,
        compliant_count=22,
        partial_count=2,
        non_compliant_count=1,
        not_applicable_count=0,
        recommendation="conditional",
        recommendation_reason="One non-compliant item can be addressed",
        clauses=sample_clauses,
        key_findings=[
            "Excellent compliance with technical specifications",
            "One minor commercial term needs clarification"
        ]
    )
    
    # Generate test report
    output_path = "/tmp/test_compliance_report.pdf"
    generator = ComplianceReportGenerator(output_path)
    generator.generate(sample_data)
    
    print(f"Test report generated: {output_path}")
