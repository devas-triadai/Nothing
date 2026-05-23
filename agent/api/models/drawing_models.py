"""
AGRA Phase 2 — Drawing Analyzer Models
Pydantic models for structured drawing analysis output.
"""

from datetime import datetime
from typing import Optional, List, Literal
from enum import Enum
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
#  Drawing Type Enumeration
# ═══════════════════════════════════════════════════════════════

class DrawingType(str, Enum):
    """Enumeration of supported drawing types."""
    GENERAL_ARRANGEMENT = "general_arrangement"
    PIPING_DIAGRAM = "piping_diagram"
    ELECTRICAL_SCHEMATIC = "electrical_schematic"
    STRUCTURAL_DRAWING = "structural_drawing"
    EQUIPMENT_LAYOUT = "equipment_layout"
    TITLE_BLOCK_ONLY = "title_block_only"
    UNKNOWN = "unknown"


class DrawingFeature(str, Enum):
    """Features that can be detected in drawings."""
    HULL_PROFILE = "hull_profile"
    DIMENSION_LINES = "dimension_lines"
    TITLE_BLOCK = "title_block"
    EQUIPMENT_SYMBOLS = "equipment_symbols"
    PIPING_RUNS = "piping_runs"
    VALVE_SYMBOLS = "valve_symbols"
    WIRING_CIRCUITS = "wiring_circuits"
    WELD_SYMBOLS = "weld_symbols"
    SECTION_VIEWS = "section_views"
    STAMP_ANNOTATIONS = "stamp_annotations"


# ═══════════════════════════════════════════════════════════════
#  Measurement & Dimension Models
# ═══════════════════════════════════════════════════════════════

class MeasurementUnit(str, Enum):
    """Standard measurement units."""
    MILLIMETER = "mm"
    CENTIMETER = "cm"
    METER = "m"
    INCH = "in"
    FOOT = "ft"
    FOOT_INCH = "ft_in"


class Dimension(BaseModel):
    """A single dimension measurement from a drawing."""
    name: str = Field(..., description="Name of the dimension (e.g., 'Overall Length')")
    value: float = Field(..., description="Numeric value of the dimension")
    unit: MeasurementUnit = Field(default=MeasurementUnit.METER)
    tolerance: Optional[str] = Field(None, description="Tolerance specification (e.g., '±0.5')")
    raw_text: str = Field(..., description="Exact text as extracted from drawing")
    location: Optional[str] = Field(None, description="General location in drawing (e.g., 'title block', 'hull profile')")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Overall Length",
                "value": 105.5,
                "unit": "m",
                "tolerance": "±0.2",
                "raw_text": "105.5 m ±0.2",
                "location": "title block",
                "confidence": 0.98
            }
        }


class ToleranceSpec(BaseModel):
    """Parsed tolerance specification."""
    nominal_value: float
    plus_tolerance: Optional[float] = None
    minus_tolerance: Optional[float] = None
    symmetric_tolerance: Optional[float] = None
    unit: MeasurementUnit


# ═══════════════════════════════════════════════════════════════
#  Title Block & Metadata Models
# ═══════════════════════════════════════════════════════════════

class TitleBlock(BaseModel):
    """Title block metadata extracted from drawing."""
    project_name: Optional[str] = Field(None, description="Project or contract name")
    vessel_name: Optional[str] = Field(None, description="Vessel name or identifier")
    drawing_number: Optional[str] = Field(None, description="Drawing number/identifier")
    drawing_title: Optional[str] = Field(None, description="Title of the drawing")
    revision: Optional[str] = Field(None, description="Revision code (e.g., 'A', 'Rev 1')")
    scale: Optional[str] = Field(None, description="Scale (e.g., '1:100')")
    date: Optional[str] = Field(None, description="Date on drawing")
    drawn_by: Optional[str] = Field(None, description="Drafter/designer name")
    checked_by: Optional[str] = Field(None, description="Checker name")
    approved_by: Optional[str] = Field(None, description="Approver name")
    company: Optional[str] = Field(None, description="Company/shipyard name")
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="How complete the title block extraction was")


# ═══════════════════════════════════════════════════════════════
#  Equipment & Compliance Models
# ═══════════════════════════════════════════════════════════════

class EquipmentTag(BaseModel):
    """Equipment tag identifier found in drawing."""
    tag_id: str = Field(..., description="Equipment tag number/identifier")
    description: Optional[str] = Field(None, description="Description of equipment")
    location: Optional[str] = Field(None, description="Location in vessel/drawing")
    confidence: float = Field(..., ge=0.0, le=1.0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "tag_id": "P-101",
                "description": "Main Fire Pump",
                "location": "Engine Room",
                "confidence": 0.92
            }
        }


class ComplianceNote(BaseModel):
    """Compliance or regulatory note found in drawing."""
    standard_reference: Optional[str] = Field(None, description="Standard name (e.g., 'SOLAS', 'ISO 8861')")
    clause_reference: Optional[str] = Field(None, description="Specific clause/section")
    requirement_text: Optional[str] = Field(None, description="Text of requirement")
    status: Literal["compliant", "non_compliant", "partial", "unverified"] = Field(default="unverified")
    confidence: float = Field(..., ge=0.0, le=1.0)


# ═══════════════════════════════════════════════════════════════
#  Confidence & Quality Models
# ═══════════════════════════════════════════════════════════════

class StageConfidence(BaseModel):
    """Confidence score for a specific processing stage."""
    stage_name: str = Field(..., description="Name of processing stage")
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: Literal["success", "partial", "failed"] = Field(default="success")
    details: Optional[str] = Field(None, description="Additional details about this stage")


class AnalysisConfidence(BaseModel):
    """Comprehensive confidence breakdown for drawing analysis."""
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Weighted overall confidence")
    drawing_type_confidence: float = Field(..., ge=0.0, le=1.0)
    ocr_confidence: float = Field(..., ge=0.0, le=1.0)
    vlm_confidence: float = Field(..., ge=0.0, le=1.0)
    validation_score: float = Field(..., ge=0.0, le=1.0)
    title_block_completeness: float = Field(..., ge=0.0, le=1.0)
    stage_scores: List[StageConfidence] = Field(default_factory=list)
    
    def get_quality_label(self) -> str:
        """Return UI-friendly quality label."""
        if self.overall_confidence >= 0.90:
            return "High Confidence"
        elif self.overall_confidence >= 0.75:
            return "Good Confidence"
        elif self.overall_confidence >= 0.60:
            return "Moderate Confidence"
        else:
            return "Low Confidence — Manual Review Recommended"
    
    def get_color_code(self) -> str:
        """Return hex color code for UI display."""
        if self.overall_confidence >= 0.90:
            return "#22c55e"  # Green
        elif self.overall_confidence >= 0.75:
            return "#eab308"  # Yellow
        elif self.overall_confidence >= 0.60:
            return "#f97316"  # Orange
        else:
            return "#ef4444"  # Red


# ═══════════════════════════════════════════════════════════════
#  Main Analysis Result Model
# ═══════════════════════════════════════════════════════════════

class DrawingAnalysisResult(BaseModel):
    """Top-level container for drawing analysis results."""
    
    # Identification
    analysis_id: str = Field(..., description="Unique analysis job ID")
    filename: str = Field(..., description="Original filename")
    drawing_type: DrawingType = Field(default=DrawingType.UNKNOWN)
    drawing_type_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    detected_features: List[DrawingFeature] = Field(default_factory=list)
    
    # Extracted Data
    title_block: Optional[TitleBlock] = None
    dimensions: List[Dimension] = Field(default_factory=list)
    equipment_tags: List[EquipmentTag] = Field(default_factory=list)
    compliance_notes: List[ComplianceNote] = Field(default_factory=list)
    
    # Quality & Confidence
    confidence: AnalysisConfidence = Field(..., description="Complete confidence breakdown")
    
    # Processing Metadata
    processing_time_ms: Optional[float] = None
    ocr_metadata: Optional[dict] = Field(None, description="Raw OCR metadata for traceability")
    recommended_analysis: str = Field(default="full_extraction", description="Recommended follow-up analysis type")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "GA-001-REV-A.pdf",
                "drawing_type": "general_arrangement",
                "drawing_type_confidence": 0.94,
                "detected_features": ["hull_profile", "dimension_lines", "title_block"],
                "title_block": {
                    "project_name": "OPV Construction",
                    "vessel_name": "ICGS Sarthi",
                    "drawing_number": "GA-001-REV-A",
                    "scale": "1:100",
                    "completeness_score": 0.85
                },
                "dimensions": [
                    {
                        "name": "Overall Length",
                        "value": 105.5,
                        "unit": "m",
                        "confidence": 0.98
                    }
                ],
                "confidence": {
                    "overall_confidence": 0.91,
                    "drawing_type_confidence": 0.94,
                    "ocr_confidence": 0.87,
                    "vlm_confidence": 0.93,
                    "validation_score": 0.90,
                    "title_block_completeness": 0.85
                },
                "created_at": "2024-05-23T18:30:00Z"
            }
        }


# ═══════════════════════════════════════════════════════════════
#  API Request/Response Models
# ═══════════════════════════════════════════════════════════════

class DrawingAnalysisRequest(BaseModel):
    """Request model for drawing analysis endpoint."""
    preferred_type: Optional[DrawingType] = Field(None, description="Optional hint for drawing type")
    extract_title_block: bool = Field(default=True)
    extract_dimensions: bool = Field(default=True)
    extract_equipment_tags: bool = Field(default=True)
    extract_compliance_notes: bool = Field(default=False)
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class DrawingAnalysisResponse(BaseModel):
    """Response model for drawing analysis endpoint."""
    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    result: Optional[DrawingAnalysisResult] = None
    error_message: Optional[str] = None
    estimated_completion_seconds: Optional[int] = None


# ═══════════════════════════════════════════════════════════════
#  Chat Integration Models
# ═══════════════════════════════════════════════════════════════

class ChatDrawingAnalysis(BaseModel):
    """Simplified drawing analysis for chat display."""
    drawing_type: str
    type_confidence: float
    vessel_name: Optional[str] = None
    drawing_number: Optional[str] = None
    key_dimensions: List[dict] = Field(default_factory=list)
    equipment_count: int = 0
    overall_confidence: float
    quality_label: str
    summary_text: str = Field(..., description="Markdown summary for chat")


# ═══════════════════════════════════════════════════════════════
#  Legacy Compatibility
# ═══════════════════════════════════════════════════════════════

class LegacyDrawingResult(BaseModel):
    """Backward-compatible result format matching existing drawing.py output."""
    dimensions: List[str] = Field(default_factory=list)
    tolerances: List[str] = Field(default_factory=list)
    materials: List[str] = Field(default_factory=list)
    equipment_tags: List[str] = Field(default_factory=list)
    compliance_notes: List[str] = Field(default_factory=list)
    _ocr_metadata: Optional[dict] = None
