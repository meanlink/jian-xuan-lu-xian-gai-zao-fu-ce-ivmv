import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, CalibrationBasis, CalibrationSegment, TimingBatch, TimingRecord
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.services import timing
from src.schemas.timing import TimingBatchInput, SegmentSetInput
from src.utils.security import hash_password
from src.utils.serialization import checksum
TIMING_BATCH_NAME='11 月设备测时批次 · 待校准'
def seed_timing(db,admin):
    """设备测时演示：TC-01 分两段校时（跨段累计），TC-02 留有缺口阻塞放行。幂等，不覆盖用户修改。"""
    if db.scalar(select(TimingBatch).where(TimingBatch.name==TIMING_BATCH_NAME)):return
    if not db.scalar(select(CalibrationBasis).where(CalibrationBasis.device=='TC-01',CalibrationBasis.boot_no=='B1101')):
        timing.register_segments(db,SegmentSetInput(device='TC-01',boot_no='B1101',segments=[{'start_tick':0,'end_tick':250000,'seconds_per_tick':0.001},{'start_tick':250000,'end_tick':600000,'seconds_per_tick':0.00102}]),admin)
    if not db.scalar(select(CalibrationBasis).where(CalibrationBasis.device=='TC-02',CalibrationBasis.boot_no=='B0902')):
        timing.register_segments(db,SegmentSetInput(device='TC-02',boot_no='B0902',segments=[{'start_tick':0,'end_tick':400000,'seconds_per_tick':0.00098}]),admin)
    teams=['一组','二组','三组','四组'];records=[]
    for i in range(6):
        records.append({'operator':f'OP-{101+i}','team':teams[i%4],'device':'TC-01','boot_no':'B1101','before_start':40000+i*3000,'before_end':440000+i*7000,'after_start':50000+i*2500,'after_end':425000+i*5500})
    for i in range(2):
        records.append({'operator':f'OP-{107+i}','team':teams[(6+i)%4],'device':'TC-02','boot_no':'B0902','before_start':20000+i*1000,'before_end':380000+i*1000,'after_start':25000+i*1000,'after_end':370000+i*1000})
    for i in range(2):
        records.append({'operator':f'OP-{109+i}','team':teams[(8+i)%4],'device':'TC-02','boot_no':'B0902','before_start':20000,'before_end':380000,'after_start':30000,'after_end':460000})
    batch=timing.create_batch(db,TimingBatchInput(name=TIMING_BATCH_NAME,source='TC-export-202611.csv',records=records),admin)
    timing.convert_batch(db,batch,'seed')
def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        admin=db.scalar(select(User).where(User.role=='admin'))
        seed_timing(db,admin)
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,CalibrationBasis,CalibrationSegment,TimingBatch,TimingRecord]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
