"""
Generiert das Notfall-Schlüssel-PDF (analog zu 1Passwords Emergency Kit).
Enthält den Master-Key als Klartext + QR-Code für einfaches Einscannen.
"""
import io
from datetime import date

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_emergency_kit_pdf(master_key_b64: str, app_title: str = "NiceApp") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25 * mm,
        leftMargin=25 * mm,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
    )

    styles = getSampleStyleSheet()
    W = 155 * mm  # nutzbare Breite

    title_style = ParagraphStyle(
        "EKTitle",
        parent=styles["Normal"],
        fontSize=20,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e3a5f"),
        leading=26,
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "EKSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica",
        textColor=colors.HexColor("#475569"),
        leading=16,
        spaceAfter=2,
        alignment=TA_CENTER,
    )
    label_style = ParagraphStyle(
        "EKLabel",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e3a5f"),
        spaceAfter=3,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "EKBody",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.HexColor("#334155"),
        leading=15,
        spaceAfter=3,
        alignment=TA_LEFT,
    )
    warning_style = ParagraphStyle(
        "EKWarning",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        leading=14,
        alignment=TA_LEFT,
    )
    mono_style = ParagraphStyle(
        "EKMono",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Courier-Bold",
        textColor=colors.HexColor("#1e293b"),
        leading=18,
        alignment=TA_CENTER,
    )

    # QR-Code generieren
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=6,
        border=2,
    )
    qr.add_data(master_key_b64)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Notfall-Schlüssel-Dokument", title_style))
    story.append(Paragraph(app_title, subtitle_style))
    story.append(Paragraph(f"Erstellt am: {date.today().strftime('%d.%m.%Y')}", subtitle_style))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 6 * mm))

    # ── Warnbox ───────────────────────────────────────────────────────────────
    warn_text = (
        "<b>WICHTIG – Sicher aufbewahren:</b> Dieses Dokument enthält den Master-Schlüssel "
        f"für die gesamte Datenverschlüsselung von {app_title}. Ohne diesen Schlüssel sind "
        "alle verschlüsselten Patientendaten dauerhaft nicht zugänglich. Drucken Sie dieses "
        "Dokument aus und bewahren Sie es an einem sicheren physischen Ort auf "
        "(Tresor, Bankschließfach)."
    )
    warn_table = Table([[Paragraph(warn_text, warning_style)]], colWidths=[W])
    warn_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#f59e0b")),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(warn_table)
    story.append(Spacer(1, 8 * mm))

    # ── Key-Box ───────────────────────────────────────────────────────────────
    story.append(Paragraph("Master-Schlüssel (Base64, 256 Bit)", label_style))
    story.append(Paragraph(
        "Tragen Sie diesen Wert in die .env-Datei ein: <font name='Courier'>ENCRYPTION_MASTER_KEY=&lt;Key&gt;</font>",
        body_style,
    ))
    key_table = Table([[Paragraph(master_key_b64, mono_style)]], colWidths=[W])
    key_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f7ff")),
        ("BOX", (0, 0), (-1, -1), 2, colors.HexColor("#0078d4")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(key_table)
    story.append(Spacer(1, 8 * mm))

    # ── QR-Code ───────────────────────────────────────────────────────────────
    story.append(Paragraph("QR-Code (schnelles Einscannen)", label_style))
    qr_image = Image(qr_buf, width=52 * mm, height=52 * mm)
    qr_image.hAlign = "LEFT"
    story.append(qr_image)
    story.append(Spacer(1, 8 * mm))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 5 * mm))

    # ── Wiederherstellung ─────────────────────────────────────────────────────
    story.append(Paragraph("Wiederherstellung", label_style))
    recovery_steps = (
        "1. Öffnen Sie die Datei <font name='Courier'>.env</font> im Stammverzeichnis der Anwendung.<br/>"
        "2. Fügen Sie folgende Zeile ein (oder ersetzen Sie den bestehenden Wert):<br/><br/>"
        f"&nbsp;&nbsp;&nbsp;<font name='Courier'>ENCRYPTION_MASTER_KEY={master_key_b64}</font><br/><br/>"
        "3. Starten Sie die Anwendung neu.<br/>"
        "4. Alle verschlüsselten Patientendaten sind wieder zugänglich."
    )
    story.append(Paragraph(recovery_steps, body_style))

    doc.build(story)
    return buffer.getvalue()
