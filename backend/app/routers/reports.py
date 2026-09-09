"""
Quarterly and monthly market report endpoints for MOG division KPI.
Generates Word documents with price statistics, product trends, and market developments.
"""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db
from app.auth import get_current_user, get_current_admin
from app.report_generator import (
    generate_quarterly_report,
    save_quarterly_report,
    list_generated_reports,
    get_benchmark_stats,
    get_product_stats,
    get_quarter_date_range,
    get_month_date_range,
)
from app.monthly_report_generator import save_monthly_report
from app.config import QUARTER_MONTHS

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)])

REPORT_MODES = ("data_only", "ai_enhanced")


def _validate_mode(mode: str):
    if mode not in REPORT_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {REPORT_MODES}")


class ReportPreviewRequest(BaseModel):
    year: int
    quarter: str


class ReportPreviewResponse(BaseModel):
    year: int
    quarter: str
    benchmarks: List[dict]
    products: List[dict]


class ReportGenerateRequest(BaseModel):
    year: int
    quarter: str
    outlook_notes: str = ""
    generated_by: str = "MOG Analyst"
    mode: str = "data_only"


class MonthlyPreviewRequest(BaseModel):
    year: int
    month: int


class MonthlyPreviewResponse(BaseModel):
    year: int
    month: int
    benchmarks: List[dict]
    products: List[dict]


class MonthlyGenerateRequest(BaseModel):
    year: int
    month: int
    generated_by: str = "MOG Analyst"
    mode: str = "data_only"


@router.post("/preview", response_model=ReportPreviewResponse)
def preview_quarterly_report(req: ReportPreviewRequest, db: Session = Depends(get_db)):
    """Preview benchmark and product stats for a quarterly report (no file generated)."""
    if req.quarter not in QUARTER_MONTHS:
        raise HTTPException(status_code=400, detail=f"Invalid quarter: {req.quarter}")

    start, end = get_quarter_date_range(req.year, req.quarter)
    b_stats = get_benchmark_stats(db, start, end)
    p_stats = get_product_stats(db, start, end)

    return ReportPreviewResponse(
        year=req.year,
        quarter=req.quarter,
        benchmarks=[{k: v for k, v in s.items() if k != "series"} for s in b_stats],
        products=[{k: v for k, v in s.items() if k != "series"} for s in p_stats],
    )


@router.post("/generate", dependencies=[Depends(get_current_admin)])
def generate_and_save_report(req: ReportGenerateRequest, db: Session = Depends(get_db)):
    """Generate and save a quarterly report to disk."""
    if req.quarter not in QUARTER_MONTHS:
        raise HTTPException(status_code=400, detail=f"Invalid quarter: {req.quarter}")
    _validate_mode(req.mode)

    try:
        filepath = save_quarterly_report(
            db,
            year=req.year,
            quarter=req.quarter,
            outlook_notes=req.outlook_notes,
            generated_by=req.generated_by,
            mode=req.mode,
        )
        return {
            "status": "success",
            "filename": filepath.name,
            "path": str(filepath),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(ex)}")


@router.post("/monthly/preview", response_model=MonthlyPreviewResponse)
def preview_monthly_report(req: MonthlyPreviewRequest, db: Session = Depends(get_db)):
    """Preview benchmark and product stats for a monthly report (no file generated)."""
    if not 1 <= req.month <= 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")

    start, end = get_month_date_range(req.year, req.month)
    b_stats = get_benchmark_stats(db, start, end)
    p_stats = get_product_stats(db, start, end)

    return MonthlyPreviewResponse(
        year=req.year,
        month=req.month,
        benchmarks=[{k: v for k, v in s.items() if k != "series"} for s in b_stats],
        products=[{k: v for k, v in s.items() if k != "series"} for s in p_stats],
    )


@router.post("/monthly/generate", dependencies=[Depends(get_current_admin)])
def generate_and_save_monthly_report(req: MonthlyGenerateRequest, db: Session = Depends(get_db)):
    """Generate and save a monthly report to disk."""
    if not 1 <= req.month <= 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    _validate_mode(req.mode)

    try:
        filepath = save_monthly_report(
            db, year=req.year, month=req.month, generated_by=req.generated_by, mode=req.mode,
        )
        return {
            "status": "success",
            "filename": filepath.name,
            "path": str(filepath),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(ex)}")


@router.get("/list")
def list_reports():
    """List all generated reports (quarterly and monthly)."""
    reports = list_generated_reports()
    return {
        "reports": [
            {
                "filename": r.name,
                "size": r.stat().st_size,
                "created": datetime.fromtimestamp(r.stat().st_mtime).isoformat(),
            }
            for r in reports
        ]
    }


@router.get("/download/{filename}", dependencies=[Depends(get_current_admin)])
def download_report(filename: str):
    """Download a generated report."""
    try:
        filepath = None
        for report in list_generated_reports():
            if report.name == filename:
                filepath = report
                break

        if not filepath or not filepath.exists():
            raise HTTPException(status_code=404, detail=f"Report not found: {filename}")

        return FileResponse(
            filepath,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
        )
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to download report: {str(ex)}")
