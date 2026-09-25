from datetime import date, datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models import MonthlyReport, MonthlyReportStatus
from ..services.docx_generator import generate_monthly_report_docx
from ..services.monthly_report_service import (
    finalize_monthly_report,
    get_monthly_report_data,
    get_or_create_monthly_report,
    reopen_monthly_report,
    update_monthly_report_content,
)
from ..permissions import chef_service_required

monthly_reports_blueprint = Blueprint(
    "monthly_reports",
    __name__,
    url_prefix="/monthly-reports",
)


@monthly_reports_blueprint.get("")
@login_required
def list_monthly_reports():
    """Liste des rapports mensuels départementaux (CDC Section 17 & 28)."""
    reports = (
        db.session.query(MonthlyReport)
        .order_by(MonthlyReport.year.desc(), MonthlyReport.month.desc())
        .all()
    )

    today = date.today()
    current_year = today.year
    current_month = today.month

    # Mois précédent comme suggestion par défaut pour la clôture mensuelle
    if current_month == 1:
        default_gen_year = current_year - 1
        default_gen_month = 12
    else:
        default_gen_year = current_year
        default_gen_month = current_month - 1

    return render_template(
        "monthly_reports/list.html",
        reports=reports,
        current_year=current_year,
        default_gen_year=default_gen_year,
        default_gen_month=default_gen_month,
    )


@monthly_reports_blueprint.post("/generate")
@login_required
@chef_service_required
def generate_monthly_report_route():
    """Génération ou rattachement d'un rapport mensuel pour un mois donné (RB-025, RB-026)."""
    year = request.form.get("year", type=int)
    month = request.form.get("month", type=int)

    if not year or not month or not (1 <= month <= 12):
        flash("Année et mois invalides.", "error")
        return redirect(url_for("monthly_reports.list_monthly_reports"))

    report, created = get_or_create_monthly_report(
        year=year,
        month=month,
        current_user=current_user,
    )

    if created:
        flash(f"Le rapport mensuel départemental pour {report.month_name} {report.year} a été créé en brouillon.", "success")
    else:
        flash(f"Le rapport mensuel pour {report.month_name} {report.year} est ouvert pour consultation.", "info")

    return redirect(url_for("monthly_reports.detail_monthly_report", id=report.id))


@monthly_reports_blueprint.get("/<int:id>")
@login_required
def detail_monthly_report(id: int):
    """Consultation détaillée du rapport mensuel départemental."""
    report = db.session.get(MonthlyReport, id)
    if report is None:
        abort(404)

    data = get_monthly_report_data(report)
    return render_template(
        "monthly_reports/detail.html",
        report=report,
        data=data,
    )


@monthly_reports_blueprint.get("/<int:id>/edit")
@login_required
@chef_service_required
def edit_monthly_report(id: int):
    """Formulaire d'ajustement rédactionnel du rapport mensuel (RB-027)."""
    report = db.session.get(MonthlyReport, id)
    if report is None:
        abort(404)

    if report.status == MonthlyReportStatus.FINALISE:
        flash("Ce rapport mensuel est déjà finalisé. Vous devez d'abord le réouvrir en brouillon pour le modifier.", "warning")
        return redirect(url_for("monthly_reports.detail_monthly_report", id=report.id))

    data = get_monthly_report_data(report)
    return render_template(
        "monthly_reports/edit.html",
        report=report,
        data=data,
    )


@monthly_reports_blueprint.post("/<int:id>/edit")
@login_required
@chef_service_required
def save_monthly_report(id: int):
    """Enregistre les ajustements apportés par le chef de service."""
    report = db.session.get(MonthlyReport, id)
    if report is None:
        abort(404)

    if report.status == MonthlyReportStatus.FINALISE:
        flash("Impossible de modifier un rapport finalisé sans réouverture préalable.", "error")
        return redirect(url_for("monthly_reports.detail_monthly_report", id=report.id))

    update_monthly_report_content(report, request.form, current_user)
    flash("Les ajustements du rapport mensuel ont été enregistrés avec succès.", "success")
    return redirect(url_for("monthly_reports.detail_monthly_report", id=report.id))


@monthly_reports_blueprint.post("/<int:id>/finalize")
@login_required
@chef_service_required
def finalize_report_action(id: int):
    """Finalisation officielle du rapport mensuel départemental (RB-027)."""
    report = db.session.get(MonthlyReport, id)
    if report is None:
        abort(404)

    try:
        finalize_monthly_report(report, current_user)
        flash(f"Le rapport mensuel départemental de {report.month_name} {report.year} est officiellement finalisé.", "success")
    except ValueError as e:
        flash(str(e), "error")

    return redirect(url_for("monthly_reports.detail_monthly_report", id=report.id))


@monthly_reports_blueprint.post("/<int:id>/reopen")
@login_required
@chef_service_required
def reopen_report_action(id: int):
    """Réouverture d'un rapport mensuel pour ajustements complémentaires."""
    report = db.session.get(MonthlyReport, id)
    if report is None:
        abort(404)

    try:
        reopen_monthly_report(report, current_user)
        flash(f"Le rapport de {report.month_name} {report.year} a été réouvert en brouillon pour ajustement.", "info")
    except ValueError as e:
        flash(str(e), "error")

    return redirect(url_for("monthly_reports.detail_monthly_report", id=report.id))


@monthly_reports_blueprint.get("/<int:id>/export-docx")
@login_required
def export_docx(id: int):
    """Export du rapport mensuel au format Microsoft Word .docx officiel (CDC Section 29)."""
    report = db.session.get(MonthlyReport, id)
    if report is None:
        abort(404)

    data = get_monthly_report_data(report)
    buffer = generate_monthly_report_docx(report, data)

    filename = f"rapport_mensuel_{report.month:02d}_{report.year}.docx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
