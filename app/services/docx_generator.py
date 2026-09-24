import io
import xml.sax.saxutils as xml_escape
import zipfile
from datetime import date, datetime
from typing import Any

from ..models import TaskStatus, WeeklyReport, WeeklyReportStatus


def _esc(val: Any) -> str:
    """Échappe les caractères réservés XML de manière sûre."""
    if val is None:
        return ""
    text = str(val)
    return xml_escape.escape(text)


def _fmt_date(d: date | datetime | None) -> str:
    if not d:
        return "-"
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y %H:%M")
    return d.strftime("%d/%m/%Y")


def _p(
    text: str = "",
    size: int = 22,
    bold: bool = False,
    italic: bool = False,
    color: str = "333333",
    align: str = "left",
    space_before: int = 60,
    space_after: int = 60,
) -> str:
    align_xml = f'<w:jc w:val="{align}"/>' if align != "left" else ""
    rpr_items = [f'<w:color w:val="{color}"/>', f'<w:sz w:val="{size}"/>']
    if bold:
        rpr_items.append("<w:b/>")
    if italic:
        rpr_items.append("<w:i/>")
    rpr_xml = f"<w:rPr>{''.join(rpr_items)}</w:rPr>"

    p_pr = f"<w:pPr>{align_xml}<w:spacing w:before=\"{space_before}\" w:after=\"{space_after}\"/></w:pPr>"
    runs = f"<w:r>{rpr_xml}<w:t xml:space=\"preserve\">{_esc(text)}</w:t></w:r>" if text else ""
    return f"<w:p>{p_pr}{runs}</w:p>"


def _heading(text: str, level: int = 1) -> str:
    if level == 1:
        return _p(
            text,
            size=28,
            bold=True,
            color="1B365D",
            space_before=240,
            space_after=120,
        )
    return _p(
        text,
        size=24,
        bold=True,
        color="2C5282",
        space_before=180,
        space_after=80,
    )


def _table(
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[int] | None = None,
    header_bg: str = "1B365D",
) -> str:
    """Génère un tableau OpenXML proprement stylisé."""
    total_cols = len(headers)
    if not col_widths:
        w = 9000 // total_cols
        col_widths = [w] * total_cols

    tbl_pr = """
    <w:tblPr>
      <w:tblW w:w="9000" w:type="dxa"/>
      <w:tblBorders>
        <w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E0"/>
        <w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E0"/>
        <w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E0"/>
        <w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E0"/>
        <w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>
        <w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>
      </w:tblBorders>
      <w:tblCellMar>
        <w:top w:w="100" w:type="dxa"/>
        <w:bottom w:w="100" w:type="dxa"/>
        <w:left w:w="150" w:type="dxa"/>
        <w:right w:w="150" w:type="dxa"/>
      </w:tblCellMar>
    </w:tblPr>
    """

    grid_cols = "".join(f'<w:gridCol w:w="{w}"/>' for w in col_widths)
    tbl_grid = f"<w:tblGrid>{grid_cols}</w:tblGrid>"

    # Ligne d'en-tête
    hdr_cells = []
    for i, h in enumerate(headers):
        w = col_widths[i]
        hdr_cells.append(
            f"""<w:tc>
              <w:tcPr>
                <w:tcW w:w="{w}" w:type="dxa"/>
                <w:shd w:val="clear" w:color="auto" w:fill="{header_bg}"/>
              </w:tcPr>
              {_p(h, size=20, bold=True, color="FFFFFF", space_before=40, space_after=40)}
            </w:tc>"""
        )
    hdr_row = f"<w:tr><w:trPr><w:tblHeader/></w:trPr>{''.join(hdr_cells)}</w:tr>"

    # Lignes de données
    body_rows = []
    for r_idx, row in enumerate(rows):
        bg = "F7FAFC" if r_idx % 2 == 1 else "FFFFFF"
        cells = []
        for i, val in enumerate(row):
            w = col_widths[i]
            cells.append(
                f"""<w:tc>
                  <w:tcPr>
                    <w:tcW w:w="{w}" w:type="dxa"/>
                    <w:shd w:val="clear" w:color="auto" w:fill="{bg}"/>
                  </w:tcPr>
                  {_p(val, size=19, color="2D3748", space_before=30, space_after=30)}
                </w:tc>"""
            )
        body_rows.append(f"<w:tr>{''.join(cells)}</w:tr>")

    return f"<w:tbl>{tbl_pr}{tbl_grid}{hdr_row}{''.join(body_rows)}</w:tbl>"


def _info_card(label: str, value: str) -> str:
    return (
        f"<w:p><w:pPr><w:spacing w:before=\"80\" w:after=\"40\"/></w:pPr>"
        f"<w:r><w:rPr><w:b/><w:color w:val=\"1B365D\"/><w:sz w:val=\"22\"/></w:rPr>"
        f"<w:t xml:space=\"preserve\">{_esc(label)} : </w:t></w:r>"
        f"<w:r><w:rPr><w:color w:val=\"2D3748\"/><w:sz w:val=\"22\"/></w:rPr>"
        f"<w:t xml:space=\"preserve\">{_esc(value)}</w:t></w:r></w:p>"
    )


def generate_weekly_report_docx(report: WeeklyReport, report_data: dict[str, Any]) -> io.BytesIO:
    """Génère le document Word (.docx) du rapport hebdomadaire selon la section 16 du CDC."""
    user = report.user
    stats = report_data.get("stats", {})
    tasks = report_data.get("tasks", [])
    unexpected = report_data.get("unexpected_activities", [])

    teams_str = ", ".join(link.team.name for link in user.team_links if link.team) if user.team_links else "Non affecté"
    role_str = "Chef de service" if user.is_chef_service() else "Collaborateur"
    if any(link.is_team_lead for link in user.team_links):
        role_str = "Chef d'équipe"

    # Construction du corps du document XML
    body_elements: list[str] = []

    # En-tête de l'entreprise
    body_elements.append(_p("HÔTEL LE ZINGANA", size=32, bold=True, color="1B365D", align="center", space_before=0, space_after=40))
    body_elements.append(_p("DÉPARTEMENT COMPTABILITÉ & FINANCE", size=20, bold=True, color="4A5568", align="center", space_before=0, space_after=120))
    body_elements.append(_p("RAPPORT D'ACTIVITÉS HEBDOMADAIRE", size=28, bold=True, color="2B6CB0", align="center", space_before=80, space_after=40))
    body_elements.append(_p(f"Période du {_fmt_date(report.period_start)} au {_fmt_date(report.period_end)}", size=22, italic=True, color="718096", align="center", space_before=0, space_after=200))

    # Tableau Informations Générales
    body_elements.append(_heading("1. Informations générales", level=2))
    info_headers = ["Paramètre", "Détail"]
    info_rows = [
        ["Collaborateur", f"{user.full_name} ({user.username})"],
        ["Fonction / Rôle", role_str],
        ["Équipe(s) d'affectation", teams_str],
        ["Période couverte", f"Du {_fmt_date(report.period_start)} au {_fmt_date(report.period_end)}"],
        ["Statut du rapport", report.status.value.upper()],
        ["Date de soumission", _fmt_date(report.submitted_at)],
        ["Validation hiérarchique", f"Validé le {_fmt_date(report.validated_at)} par {report.validated_by.full_name}" if report.validated_by else "En attente de validation"],
    ]
    body_elements.append(_table(info_headers, info_rows, col_widths=[3200, 5800], header_bg="2B6CB0"))

    # Indicateurs clés / Statistiques
    body_elements.append(_heading("2. Indicateurs clés de la semaine", level=2))
    stat_headers = ["Indicateur", "Valeur"]
    stat_rows = [
        ["Total des tâches actives", str(stats.get("total_tasks", len(tasks)))],
        ["Tâches terminées", str(stats.get("completed_count", 0))],
        ["Tâches en cours", str(stats.get("in_progress_count", 0))],
        ["Tâches en retard", str(stats.get("late_count", 0))],
        ["Activités imprévues déclarées", str(len(unexpected))],
        ["Taux d'avancement moyen", f"{stats.get('average_progress', 0)} %"],
    ]
    body_elements.append(_table(stat_headers, stat_rows, col_widths=[5000, 4000], header_bg="2D3748"))

    # Section Activités Planifiées et Réalisées
    body_elements.append(_heading("3. Activités planifiées et réalisées", level=2))
    if tasks:
        task_headers = ["N°", "Tâche", "Équipe", "Échéance", "Statut", "Avancement"]
        task_rows = []
        for idx, t in enumerate(tasks, start=1):
            team_name = t.team.name if t.team else "-"
            task_rows.append([
                str(idx),
                t.title,
                team_name,
                _fmt_date(t.due_date),
                t.status.value.replace("_", " ").upper(),
                f"{int(t.progress)} %",
            ])
        body_elements.append(_table(task_headers, task_rows, col_widths=[600, 3200, 1800, 1200, 1200, 1000], header_bg="1B365D"))
    else:
        body_elements.append(_p("Aucune tâche planifiée ou traitée sur cette période.", italic=True, color="718096"))

    # Section Activités Imprévues
    body_elements.append(_heading("4. Activités imprévues", level=2))
    if unexpected:
        unexp_headers = ["N°", "Date", "Titre", "Demandeur", "Priorité", "Résultat", "Avis superviseur"]
        unexp_rows = []
        for idx, act in enumerate(unexpected, start=1):
            unexp_rows.append([
                str(idx),
                _fmt_date(act.activity_date),
                act.title,
                act.requester or "-",
                act.priority.value.upper(),
                act.result or "-",
                act.responsible_comment or "-",
            ])
        body_elements.append(_table(unexp_headers, unexp_rows, col_widths=[500, 1100, 2200, 1400, 1000, 1400, 1400], header_bg="4A5568"))
    else:
        body_elements.append(_p("Aucune activité imprévue enregistrée pour cette semaine.", italic=True, color="718096"))

    # Section Analyse & Synthèse
    body_elements.append(_heading("5. Analyse, difficultés et solutions", level=2))
    body_elements.append(_info_card("Synthèse des travaux", report.narrative_summary or "Aucune synthèse narrative rédigée."))
    body_elements.append(_info_card("Difficultés rencontrées", report.difficulties or "Aucune difficulté particulière signalée."))
    body_elements.append(_info_card("Solutions apportées / proposées", report.solutions or "Non renseigné."))
    body_elements.append(_info_card("Observations & perspectives", report.observations or "Aucune observation."))

    # Section Validation et Signatures (3 colonnes)
    body_elements.append(_heading("6. Signatures et visa hiérarchique", level=2))
    sig_headers = ["Le Collaborateur", "Le Chef d'Équipe", "Le Chef de Service"]
    collab_status = f"Soumis le {_fmt_date(report.submitted_at)}" if report.submitted_at else "Brouillon non soumis"
    cds_status = f"Validé le {_fmt_date(report.validated_at)}\npar {report.validated_by.full_name}" if report.validated_at else "En attente"

    sig_rows = [
        [
            f"{user.full_name}\n\nStatut : {collab_status}\n\nSignature : ....................",
            "Visa & Commentaires :\n\n........................................\n\nSignature : ....................",
            f"Chef de service :\n\nStatut : {cds_status}\n\nSignature : ....................",
        ]
    ]
    body_elements.append(_table(sig_headers, sig_rows, col_widths=[3000, 3000, 3000], header_bg="1B365D"))

    # Assemblage OpenXML
    doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(body_elements)}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", doc_xml)

    buffer.seek(0)
    return buffer
