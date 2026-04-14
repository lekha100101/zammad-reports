from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.deps import get_db
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/statuses")
def statuses(
    request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    return ReportService(db).tickets_by_status(date_from, date_to)


@router.get("/agents")
def agents(
    request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    return ReportService(db).tickets_by_agent(date_from, date_to)


@router.get("/groups")
def groups(
    request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    return ReportService(db).tickets_by_group(date_from, date_to)


@router.get("/organizations")
def organizations(
    request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    return ReportService(db).tickets_by_organization(date_from, date_to)


def get_report_data(report_name: str, db: Session, date_from=None, date_to=None):
    service = ReportService(db)

    if report_name == "statuses":
        return service.tickets_by_status(date_from, date_to)
    if report_name == "agents":
        return service.tickets_by_agent(date_from, date_to)
    if report_name == "groups":
        return service.tickets_by_group(date_from, date_to)
    if report_name == "organizations":
        return service.tickets_by_organization(date_from, date_to)
    if report_name == "regional-summary":
        return service.regional_period_report(date_from, date_to)
    if report_name == "sla":
        return service.sla_report(date_from, date_to)
    if report_name == "workload":
        data = service.workload_report(date_from, date_to)
        return data.get("agents", [])
    if report_name == "time-accounting":
        return service.time_accounting_report(date_from, date_to)

    raise HTTPException(status_code=404, detail="Unknown report")


@router.get("/{report_name}/export.csv")
def export_csv(
    request,
    report_name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    data = get_report_data(report_name, db, date_from, date_to)
    df = pd.DataFrame(data)

    if df.empty:
        df = pd.DataFrame([{"message": "no_data"}])

    output = BytesIO()
    output.write(df.to_csv(index=False).encode("utf-8-sig"))
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_name}.csv"'},
    )


@router.get("/{report_name}/export.xlsx")
def export_xlsx(
    request: Request,
    report_name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    data = get_report_data(report_name, db, date_from, date_to)

    normalized = []

    if report_name == "regional-summary":
        for row in data:
            items = row.get("specialist_items", [])

            if items:
                for item in items:
                    normalized.append({
                        "Регион": row.get("region", ""),
                        "Поступило": row.get("incoming_count", 0),
                        "Закрыто": row.get("closed_count", 0),
                        "Переходящие": row.get("carried_count", 0),
                        "Специалист": item.get("name", ""),
                        "Количество выполненных заявок": item.get("count", 0),
                        "Среднее время закрытия": row.get("avg_close_time", ""),
                        "Среднее время реагирования": row.get("avg_response_time", ""),
                    })
            else:
                normalized.append({
                    "Регион": row.get("region", ""),
                    "Поступило": row.get("incoming_count", 0),
                    "Закрыто": row.get("closed_count", 0),
                    "Переходящие": row.get("carried_count", 0),
                    "Специалист": "",
                    "Количество выполненных заявок": "",
                    "Среднее время закрытия": row.get("avg_close_time", ""),
                    "Среднее время реагирования": row.get("avg_response_time", ""),
                })
    else:
        normalized = data

    df = pd.DataFrame(normalized)

    if df.empty:
        df = pd.DataFrame([{"message": "no_data"}])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
        ws = writer.sheets["Report"]

        for column_cells in ws.columns:
            max_length = 0
            letter = column_cells[0].column_letter
            for cell in column_cells:
                value = "" if cell.value is None else str(cell.value)
                if len(value) > max_length:
                    max_length = len(value)
                cell.alignment = cell.alignment.copy(wrap_text=True, vertical="top")
            ws.column_dimensions[letter].width = min(max_length + 2, 40)

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{report_name}.xlsx"'
        },
    )


@router.get("/regional-summary")
def regional_summary(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    return ReportService(db).regional_period_report(date_from, date_to)
