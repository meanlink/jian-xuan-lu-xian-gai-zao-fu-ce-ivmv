from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import TimingBatch, TimingRecord, CalibrationBasis, CalibrationSegment
from src.schemas.timing import TimingBatchInput, SegmentSetInput
from src.middlewares.auth import current_user, can_write
from src.services import timing
from src.services.audit import record
from src.utils.serialization import timing_batch_dict, timing_record_dict, basis_dict, dataset_dict
router=APIRouter()
@router.get('/timing-batches')
def list_batches(db=Depends(get_db),u=Depends(current_user)):
    return [timing_batch_dict(b) for b in db.scalars(select(TimingBatch).order_by(TimingBatch.id.desc()))]
@router.post('/timing-batches',status_code=201)
def create_batch(data:TimingBatchInput,db=Depends(get_db),u=Depends(can_write)):
    b=timing.create_batch(db,data,u); record(db,u.email,'timing.import',{'id':b.id,'rows':b.total_count})
    db.commit(); return timing_batch_dict(b)
@router.get('/timing-batches/{id}')
def batch_detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    b=db.get(TimingBatch,id)
    if not b:raise HTTPException(404,'待校准批次不存在')
    rows=db.scalars(select(TimingRecord).where(TimingRecord.batch_id==id).order_by(TimingRecord.row_no)).all()
    return {**timing_batch_dict(b),'records':[timing_record_dict(r) for r in rows]}
@router.post('/timing-batches/{id}/convert')
def convert(id:int,db=Depends(get_db),u=Depends(can_write)):
    b=db.get(TimingBatch,id)
    if not b:raise HTTPException(404,'待校准批次不存在')
    stats=timing.convert_batch(db,b,u.email); record(db,u.email,'timing.convert',{'id':b.id,**stats})
    db.commit(); return {**timing_batch_dict(b),'stats':stats}
@router.post('/timing-batches/{id}/release')
def release(id:int,db=Depends(get_db),u=Depends(can_write)):
    b=db.get(TimingBatch,id)
    if not b:raise HTTPException(404,'待校准批次不存在')
    ds,created=timing.release(db,b,u); record(db,u.email,'timing.release',{'id':b.id,'dataset_id':ds.id,'created':created})
    db.commit(); return {'dataset':dataset_dict(ds),'created':created}
@router.get('/calibration/bases')
def list_bases(db=Depends(get_db),u=Depends(current_user)):
    out=[]
    for b in db.scalars(select(CalibrationBasis).order_by(CalibrationBasis.device,CalibrationBasis.boot_no)):
        segs=db.scalars(select(CalibrationSegment).where(CalibrationSegment.basis_id==b.id).order_by(CalibrationSegment.start_tick,CalibrationSegment.id)).all()
        out.append(basis_dict(b,segs))
    return out
@router.post('/calibration/segments',status_code=201)
def register(data:SegmentSetInput,db=Depends(get_db),u=Depends(can_write)):
    basis=timing.register_segments(db,data,u); record(db,u.email,'calibration.register',{'device':basis.device,'boot_no':basis.boot_no,'version':basis.version,'segments':len(data.segments)})
    db.commit()
    resumed=timing.resume_affected(db,basis.device,basis.boot_no,u.email); db.commit()
    segs=db.scalars(select(CalibrationSegment).where(CalibrationSegment.basis_id==basis.id).order_by(CalibrationSegment.start_tick,CalibrationSegment.id)).all()
    return {'basis':basis_dict(basis,segs),'resumed':resumed}
@router.delete('/calibration/segments/{sid}')
def remove_segment(sid:int,db=Depends(get_db),u=Depends(can_write)):
    basis=timing.delete_segment(db,sid); record(db,u.email,'calibration.segment.delete',{'segment_id':sid,'device':basis.device,'boot_no':basis.boot_no,'version':basis.version})
    db.commit()
    resumed=timing.resume_affected(db,basis.device,basis.boot_no,u.email); db.commit()
    segs=db.scalars(select(CalibrationSegment).where(CalibrationSegment.basis_id==basis.id).order_by(CalibrationSegment.start_tick,CalibrationSegment.id)).all()
    return {'basis':basis_dict(basis,segs),'resumed':resumed}
