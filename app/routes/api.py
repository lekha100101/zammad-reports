from io import BytesIO
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.deps import get_db
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])


def transfer_args(date_from,date_to,region,engineer_id,organization_id,ticket_number,sort_by,sort_order):
    return dict(date_from=date_from,date_to=date_to,region=region,engineer_id=engineer_id,organization_id=organization_id,ticket_number=ticket_number,sort_by=sort_by,sort_order=sort_order)


@router.get("/transfers")
def transfers(request: Request, date_from:str|None=Query(None), date_to:str|None=Query(None), region:str|None=Query(None), engineer_id:int|None=Query(None), organization_id:int|None=Query(None), ticket_number:str|None=Query(None), sort_by:str=Query("transferred_at"), sort_order:str=Query("desc"), db:Session=Depends(get_db)):
    require_user(request,db)
    return ReportService(db).ticket_transfers(**transfer_args(date_from,date_to,region,engineer_id,organization_id,ticket_number,sort_by,sort_order))


def get_report_data(report_name, db, date_from=None, date_to=None, **kwargs):
    service=ReportService(db)
    if report_name=="statuses": return service.tickets_by_status(date_from,date_to)
    if report_name=="agents": return service.tickets_by_agent(date_from,date_to)
    if report_name=="groups": return service.tickets_by_group(date_from,date_to)
    if report_name=="organizations": return service.tickets_by_organization(date_from,date_to)
    if report_name=="regional-summary": return service.regional_period_report(date_from,date_to)
    if report_name=="transfers": return service.ticket_transfers(date_from,date_to,**kwargs)
    raise HTTPException(status_code=404,detail="Unknown report")


def export_rows(report_name,data):
    if report_name=="transfers":
        return [{
            "№ заявки":r["ticket_number"],"Тема":r["title"],"Регион":r["region"],
            "Предыдущий инженер":r["previous_engineer"],"Новый инженер":r["new_engineer"],
            "Дата/время передачи":r["transferred_at"],"Инициатор":r["initiator"],
            "Медицинская организация":r["organization"],
        } for r in data]
    if report_name=="regional-summary":
        out=[]
        for row in data:
            items=row.get("specialist_items",[]) or [{"name":"","count":""}]
            for item in items:
                out.append({"Регион":row.get("region",""),"Поступило":row.get("incoming_count",0),"Закрыто":row.get("closed_count",0),"Переходящие":row.get("carried_count",0),"Специалист":item.get("name",""),"Количество выполненных заявок":item.get("count",""),"Среднее время закрытия":row.get("avg_close_time",""),"Среднее время реагирования":row.get("avg_response_time","")})
        return out
    return data


@router.get("/{report_name}/export.csv")
def export_csv(request:Request,report_name:str,date_from:str|None=Query(None),date_to:str|None=Query(None),region:str|None=Query(None),engineer_id:int|None=Query(None),organization_id:int|None=Query(None),ticket_number:str|None=Query(None),sort_by:str=Query("transferred_at"),sort_order:str=Query("desc"),db:Session=Depends(get_db)):
    require_user(request,db)
    extra=transfer_args(None,None,region,engineer_id,organization_id,ticket_number,sort_by,sort_order)
    extra.pop("date_from"); extra.pop("date_to")
    data=get_report_data(report_name,db,date_from,date_to,**extra)
    df=pd.DataFrame(export_rows(report_name,data))
    if df.empty: df=pd.DataFrame([{"message":"no_data"}])
    output=BytesIO(); output.write(df.to_csv(index=False).encode("utf-8-sig")); output.seek(0)
    return StreamingResponse(output,media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{report_name}.csv"'})


@router.get("/{report_name}/export.xlsx")
def export_xlsx(request:Request,report_name:str,date_from:str|None=Query(None),date_to:str|None=Query(None),region:str|None=Query(None),engineer_id:int|None=Query(None),organization_id:int|None=Query(None),ticket_number:str|None=Query(None),sort_by:str=Query("transferred_at"),sort_order:str=Query("desc"),db:Session=Depends(get_db)):
    require_user(request,db)
    extra=transfer_args(None,None,region,engineer_id,organization_id,ticket_number,sort_by,sort_order); extra.pop("date_from"); extra.pop("date_to")
    data=get_report_data(report_name,db,date_from,date_to,**extra)
    df=pd.DataFrame(export_rows(report_name,data))
    if df.empty: df=pd.DataFrame([{"message":"no_data"}])
    output=BytesIO()
    with pd.ExcelWriter(output,engine="openpyxl") as writer:
        df.to_excel(writer,index=False,sheet_name="Report"); ws=writer.sheets["Report"]
        for cells in ws.columns:
            letter=cells[0].column_letter; maxlen=0
            for cell in cells:
                maxlen=max(maxlen,len("" if cell.value is None else str(cell.value)))
                cell.alignment=cell.alignment.copy(wrap_text=True,vertical="top")
            ws.column_dimensions[letter].width=min(maxlen+2,50)
        ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
    output.seek(0)
    return StreamingResponse(output,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="{report_name}.xlsx"'})
