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
from ..models import Team, User, UserRole, UserTeam, WeeklyReport, WeeklyReportStatus
from ..permissions import (
    can_edit_report,
    can_submit_report,
    can_validate_report,
    can_view_report,
    chef_service_required,
)
from ..services.docx_generator import generate_weekly_report_docx
from ..services.report_service import (
    ReportValidationError,
    generate_weekly_reports_for_all,
    get_or_create_weekly_report,
    get_report_data,
    get_visible_reports,
    get_week_bounds,
    reject_weekly_report_to_draft,
    submit_weekly_report,
    update_weekly_report,
    validate_weekly_report,
)

reports_blueprint = Blueprint("reports", __name__, url_prefix="/reports")


@reports_blueprint.get("")
@login_required
def list_reports():
    status_filter = request.args.get("status")
    user_id_filter = request.args.get("user_id", type=int)
    team_id_filter = request.args.get("team_id", type=int)
    date_filter_str = request.args.get("period_start")

    period_start_filter = None
    if date_filter_str:
        try:
            period_start_filter = datetime.strptime(date_filter_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    reports = get_visible_reports(
        user=current_user,
        status=status_filter,
        team_id=team_id_filter,
        user_id=user_id_filter,
        period_start=period_start_filter,
    )

    selectable_users = []
    selectable_teams = []

    if current_user.is_chef_service():
        selectable_users = db.session.query(User).order_by(User.last_name, User.first_name).all()
        selectable_teams = db.session.query(Team).order_by(Team.name).all()
    elif any(link.is_team_lead for link in current_user.team_links):
        led_team_ids = {link.team_id for link in current_user.team_links if link.is_team_lead}
        selectable_teams = db.session.query(Team).filter(Team.id.in_(led_team_ids)).all()
        subordinate_ids = {
            link.user_id
            for link in db.session.query(UserTeam).filter(UserTeam.team_id.in_(led_team_ids)).all()
        }
        subordinate_ids.add(current_user.id)
        selectable_users = (
            db.session.query(User)
            .filter(User.id.in_(subordinate_ids))
            .order_by(User.last_name, User.first_name)
            .all()
        )

    cur_start, cur_end = get_week_bounds()
    my_current_report = (
        db.session.query(WeeklyReport)
        .filter_by(user_id=current_user.id, period_start=cur_start)
        .one_or_none()
    )

    return render_template(
        "reports/list.html",
        reports=reports,
        current_status=status_filter,
        current_user_id=user_id_filter,
        current_team_id=team_id_filter,
        current_period_start=date_filter_str,
        selectable_users=selectable_users,
        selectable_teams=selectable_teams,
        my_current_report=my_current_report,
        current_week_start=cur_start,
        current_week_end=cur_end,
    )


@reports_blueprint.get("/<int:id>")
@login_required
def detail_report(id: int):
    report = db.session.get(WeeklyReport, id)
    if report is None:
        abort(404)

    if not can_view_report(current_user, report):
        abort(403)

    report_data = get_report_data(report)

    can_edit = can_edit_report(current_user, report)
    can_submit = can_submit_report(current_user, report)
    can_validate = can_validate_report(current_user, report)
    can_reject = current_user.is_chef_service() and report.status == WeeklyReportStatus.SOUMIS

    return render_template(
        "reports/detail.html",
        report=report,
        data=report_data,
        can_edit=can_edit,
        can_submit=can_submit,
        can_validate=can_validate,
        can_reject=can_reject,
    )


@reports_blueprint.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_report(id: int):
    report = db.session.get(WeeklyReport, id)
    if report is None:
        abort(404)

    if not can_edit_report(current_user, report):
        abort(403)

    report_data = get_report_data(report)

    if request.method == "POST":
        action = request.form.get("action", "save")
        data = {
            "narrative_summary": request.form.get("narrative_summary", ""),
            "difficulties": request.form.get("difficulties", ""),
            "solutions": request.form.get("solutions", ""),
            "observations": request.form.get("observations", ""),
        }

        try:
            update_weekly_report(report, current_user, data)
            if action == "submit":
                submit_weekly_report(report, current_user)
                flash("Votre rapport hebdomadaire a été enregistré et soumis avec succès au chef de service.", "success")
            else:
                flash("Votre rapport hebdomadaire a été enregistré en brouillon.", "success")
            return redirect(url_for("reports.detail_report", id=report.id))
        except ReportValidationError as e:
            for err in e.errors:
                flash(err, "danger")

    return render_template(
        "reports/form.html",
        report=report,
        data=report_data,
    )


@reports_blueprint.post("/<int:id>/submit")
@login_required
def submit_report_action(id: int):
    report = db.session.get(WeeklyReport, id)
    if report is None:
        abort(404)

    if not can_submit_report(current_user, report):
        abort(403)

    try:
        submit_weekly_report(report, current_user)
        flash("Rapport hebdomadaire soumis avec succès pour validation.", "success")
    except ReportValidationError as e:
        for err in e.errors:
            flash(err, "danger")

    return redirect(url_for("reports.detail_report", id=report.id))


@reports_blueprint.post("/<int:id>/validate")
@login_required
def validate_report_action(id: int):
    report = db.session.get(WeeklyReport, id)
    if report is None:
        abort(404)

    if not can_validate_report(current_user, report):
        abort(403)

    observations = request.form.get("observations", "").strip()

    try:
        validate_weekly_report(report, current_user, observations=observations or None)
        flash("Le rapport hebdomadaire a été validé avec succès (RB-023).", "success")
    except ReportValidationError as e:
        for err in e.errors:
            flash(err, "danger")

    return redirect(url_for("reports.detail_report", id=report.id))


@reports_blueprint.post("/<int:id>/reject")
@login_required
def reject_report_action(id: int):
    report = db.session.get(WeeklyReport, id)
    if report is None:
        abort(404)

    if not (current_user.is_chef_service() and report.status == WeeklyReportStatus.SOUMIS):
        abort(403)

    reason = request.form.get("reason", "").strip()
    try:
        reject_weekly_report_to_draft(report, current_user, reason=reason or None)
        flash("Le rapport a été renvoyé en brouillon au collaborateur pour révision.", "info")
    except ReportValidationError as e:
        for err in e.errors:
            flash(err, "danger")

    return redirect(url_for("reports.detail_report", id=report.id))


@reports_blueprint.get("/<int:id>/export-docx")
@login_required
def export_docx(id: int):
    report = db.session.get(WeeklyReport, id)
    if report is None:
        abort(404)

    if not can_view_report(current_user, report):
        abort(403)

    report_data = get_report_data(report)
    docx_stream = generate_weekly_report_docx(report, report_data)

    safe_username = report.user.username.replace(" ", "_")
    period_str = report.period_start.strftime("%Y%m%d")
    filename = f"Rapport_Hebdo_{safe_username}_{period_str}.docx"

    return send_file(
        docx_stream,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@reports_blueprint.post("/generate-current")
@login_required
def generate_current_report():
    report, created = get_or_create_weekly_report(current_user)
    if created:
        flash("Votre rapport hebdomadaire pour la semaine en cours a été généré en brouillon.", "success")
    else:
        flash("Votre rapport hebdomadaire pour cette semaine existe déjà.", "info")
    return redirect(url_for("reports.detail_report", id=report.id))


@reports_blueprint.post("/generate-all")
@login_required
@chef_service_required
def generate_all_reports():
    reports = generate_weekly_reports_for_all()
    flash(f"Génération automatique effectuée : {len(reports)} rapport(s) hebdomadaire(s) traités pour la semaine.", "success")
    return redirect(url_for("reports.list_reports"))
