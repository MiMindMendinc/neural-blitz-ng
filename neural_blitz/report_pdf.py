"""Optional PDF report generation."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from neural_blitz.config import TestConfig
from neural_blitz.errors import DependencyMissing, MetricsError
from neural_blitz.metrics import LatencyStats

logger = logging.getLogger("neural_blitz")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, TableStyle
    from reportlab.platypus import Table as PdfTable

    PDF_REPORTS_AVAILABLE = True
except ImportError:
    PDF_REPORTS_AVAILABLE = False


def ensure_pdf_reporting_available() -> None:
    if not PDF_REPORTS_AVAILABLE:
        raise DependencyMissing("PDF reporting requires reportlab. Install with: pip install 'neural-blitz-ng[pdf]'")


def _pdf_metric_rows(stats: LatencyStats) -> list[list[str]]:
    return [
        ["Packets Sent", str(stats.count_sent)],
        ["Packets Received", str(stats.count_received)],
        ["Packet Loss", str(stats.count_lost)],
        ["Success Rate", f"{stats.success_rate:.3f}%"],
        ["Loss Rate", f"{stats.loss_rate:.3f}%"],
        ["Mean Latency", f"{stats.mean_us:.3f} us"],
        ["P95 Latency", f"{stats.p95_us:.3f} us"],
        ["P99 Latency", f"{stats.p99_us:.3f} us"],
        ["Jitter", f"{stats.jitter_us:.3f} us"],
        ["Throughput", f"{stats.pps:.3f} pps"],
        ["Duration", f"{stats.duration_s:.3f} s"],
    ]


def write_pdf_report(
    stats: LatencyStats,
    config: TestConfig,
    path: str,
    sla_failures: list[str] | None = None,
) -> None:
    ensure_pdf_reporting_available()
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "BlitzTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=colors.HexColor("#123243"),
            spaceAfter=10,
        )
        subtitle_style = ParagraphStyle(
            "BlitzSubtitle",
            parent=styles["BodyText"],
            fontSize=10,
            textColor=colors.HexColor("#556371"),
            leading=14,
            spaceAfter=8,
        )
        section_style = ParagraphStyle(
            "BlitzSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=colors.HexColor("#0f766e"),
            spaceAfter=8,
            spaceBefore=10,
        )
        body_style = ParagraphStyle(
            "BlitzBody",
            parent=styles["BodyText"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1c2b36"),
        )

        story: list[Any] = []
        doc = SimpleDocTemplate(
            str(destination),
            pagesize=letter,
            leftMargin=0.7 * inch,
            rightMargin=0.7 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.7 * inch,
            title=f"Neural Blitz NG Report - {stats.label}",
        )

        story.append(Paragraph("Neural Blitz NG Performance Report", title_style))
        story.append(
            Paragraph(
                f"Label: <b>{stats.label}</b><br/>"
                f"Target: <b>{config.host}:{config.port}</b><br/>"
                f"Generated: <b>{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}</b>",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 0.12 * inch))

        summary_table = PdfTable(
            [
                ["Profile", stats.label],
                ["Host", config.host],
                ["Port", str(config.port)],
                ["Packet Size", f"{config.size} bytes"],
                ["Concurrency", str(config.concurrency)],
                ["Rate Limit", f"{config.rate:.0f}/s" if config.rate > 0 else "Unlimited"],
            ],
            colWidths=[1.7 * inch, 4.3 * inch],
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f4f2")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8d7de")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("Measured Results", section_style))
        results_table = PdfTable(_pdf_metric_rows(stats), colWidths=[2.2 * inch, 3.8 * inch])
        results_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdd4d0"))]))
        story.append(results_table)

        if sla_failures is not None:
            story.append(Paragraph("SLA Review", section_style))
            if sla_failures:
                sla_text = "<br/>".join(f"- {f}" for f in sla_failures)
                story.append(Paragraph(f"<b>Status:</b> FAILED<br/>{sla_text}", body_style))
            else:
                story.append(Paragraph("<b>Status:</b> PASSED", body_style))

        story.append(Spacer(1, 0.3 * inch))
        story.append(
            Paragraph(
                "<i>Michigan MindMend Inc. — Neural Blitz NG — "
                "Measure the link before the outage writes the story.</i>",
                body_style,
            )
        )
        doc.build(story)
    except OSError as exc:
        raise MetricsError(f"Unable to write PDF report '{destination}': {exc}") from exc
    logger.info("PDF report written to %s", destination)
