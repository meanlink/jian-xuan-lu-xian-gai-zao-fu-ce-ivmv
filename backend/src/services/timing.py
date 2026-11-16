"""设备测时待校准区：采集器换电重启后刻度归零、刻度快慢随校时段变化，
测时刻度须按设备与开机批号登记的校时依据分段换算为秒，全批通过才放行。"""
import math
import time
from fastapi import HTTPException
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError
from src.models import CalibrationBasis, CalibrationSegment, TimingBatch, TimingRecord, Dataset
from src.utils.serialization import checksum

MEASURES = [('before', 'before_start', 'before_end', '原路线'), ('after', 'after_start', 'after_end', '新路线')]
TEXT_FIELDS = [('operator', '匿名作业员'), ('team', '试点小组'), ('device', '采集设备'), ('boot_no', '开机批号')]
TICK_FIELDS = [('before_start', '原路线起始刻度'), ('before_end', '原路线结束刻度'), ('after_start', '新路线起始刻度'), ('after_end', '新路线结束刻度')]


def _tick(v):
    return f'{v:g}'


def _fmt_intervals(intervals):
    shown = '、'.join(f'[{_tick(a)}, {_tick(b)}]' for a, b in intervals[:3])
    return shown + (f' 等 {len(intervals)} 处' if len(intervals) > 3 else '')


def create_batch(db, data, user):
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(TimingBatch).where(TimingBatch.name == name)):
        raise HTTPException(409, '该待校准批次名已存在，请修改名称')
    rows = [_validate_row(row, i) for i, row in enumerate(data.records)]
    batch = TimingBatch(name=name, source=data.source, status='pending', total_count=len(rows), created_by=user.email, created_at=time.time())
    db.add(batch)
    db.flush()
    for i, row in enumerate(rows):
        db.add(TimingRecord(batch_id=batch.id, row_no=i + 1, **row, updated_at=time.time()))
    db.flush()
    return batch


def _validate_row(row, index):
    label = f'第 {index + 1} 行'
    out = {}
    for key, cname in TEXT_FIELDS:
        value = str(row.get(key) or '').strip()
        if not value:
            raise HTTPException(422, f'{label}缺少字段 {cname}')
        out[key] = value
    for key, cname in TICK_FIELDS:
        value = row.get(key)
        try:
            if isinstance(value, bool) or value is None or value == '':
                raise ValueError()
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise HTTPException(422, f'{label} {cname} 必须为不小于 0 的有限数值')
        out[key] = value
    if not out['before_start'] < out['before_end']:
        raise HTTPException(422, f'{label} 原路线测量起止刻度颠倒或相等')
    if not out['after_start'] < out['after_end']:
        raise HTTPException(422, f'{label} 新路线测量起止刻度颠倒或相等')
    return out


def register_segments(db, data, user):
    """按设备与开机批号登记刻度区间与每刻度秒数；同一批登记自相重叠直接拒绝，
    与既有区间的重叠保留为冲突状态，在换算与放行时阻止并可在校准页作废。"""
    device, boot_no = data.device.strip(), data.boot_no.strip()
    if not device or not boot_no:
        raise HTTPException(422, '设备与开机批号不能为空')
    segs = []
    for i, s in enumerate(data.segments):
        label = f'第 {i + 1} 段'
        for value, cname in [(s.start_tick, '起始刻度'), (s.end_tick, '结束刻度'), (s.seconds_per_tick, '每刻度秒数')]:
            if not math.isfinite(value):
                raise HTTPException(422, f'{label} {cname} 必须为有限数值')
        if not 0 <= s.start_tick < s.end_tick:
            raise HTTPException(422, f'{label} 刻度区间起止颠倒或相等')
        if s.seconds_per_tick <= 0:
            raise HTTPException(422, f'{label} 每刻度秒数必须为正数')
        segs.append({'start_tick': s.start_tick, 'end_tick': s.end_tick, 'seconds_per_tick': s.seconds_per_tick})
    segs.sort(key=lambda x: x['start_tick'])
    for i in range(1, len(segs)):
        if segs[i]['start_tick'] < segs[i - 1]['end_tick']:
            a, b = segs[i - 1], segs[i]
            raise HTTPException(409, f'本次登记的区间 [{_tick(a["start_tick"])}, {_tick(a["end_tick"])}] 与 [{_tick(b["start_tick"])}, {_tick(b["end_tick"])}] 自相重叠，请修正后重新登记')
    basis = _lock_basis(db, device, boot_no)
    version = _bump_version(db, basis)
    for s in segs:
        db.add(CalibrationSegment(basis_id=basis.id, device=device, boot_no=boot_no, version=version, created_by=user.email, created_at=time.time(), **s))
    db.flush()
    return basis


def delete_segment(db, segment_id):
    seg = db.get(CalibrationSegment, segment_id)
    if not seg:
        raise HTTPException(404, '校时区间不存在')
    basis = db.scalars(select(CalibrationBasis).where(CalibrationBasis.id == seg.basis_id).with_for_update()).first()
    db.delete(seg)
    _bump_version(db, basis)
    db.flush()
    return basis


def _bump_version(db, basis):
    """依据版本原子自增并读回：并发登记在任意数据库上都不会丢失版本号。"""
    db.execute(update(CalibrationBasis).where(CalibrationBasis.id == basis.id)
               .values(version=CalibrationBasis.version + 1, updated_at=time.time()))
    db.flush()
    db.refresh(basis)
    return basis.version


def _lock_basis(db, device, boot_no):
    """读取并锁定该设备与开机批号的依据行（不存在则创建），使并发登记/放行串行。"""
    basis = db.scalars(select(CalibrationBasis).where(CalibrationBasis.device == device, CalibrationBasis.boot_no == boot_no).with_for_update()).first()
    if basis:
        return basis
    try:
        with db.begin_nested():
            basis = CalibrationBasis(device=device, boot_no=boot_no, version=0, updated_at=time.time())
            db.add(basis)
            db.flush()
    except IntegrityError:
        basis = db.scalars(select(CalibrationBasis).where(CalibrationBasis.device == device, CalibrationBasis.boot_no == boot_no).with_for_update()).first()
    return basis


def _basis_map(db, pairs, lock=False):
    """pairs: {(device, boot_no)} → {'version': int|None, 'segments': [...]}。按字典序加锁避免死锁。"""
    out = {}
    for device, boot_no in sorted(pairs):
        stmt = select(CalibrationBasis).where(CalibrationBasis.device == device, CalibrationBasis.boot_no == boot_no)
        basis = db.scalars(stmt.with_for_update() if lock else stmt).first()
        if not basis:
            out[(device, boot_no)] = {'version': None, 'segments': []}
            continue
        segs = db.scalars(select(CalibrationSegment).where(CalibrationSegment.basis_id == basis.id).order_by(CalibrationSegment.start_tick, CalibrationSegment.id)).all()
        out[(device, boot_no)] = {'version': basis.version, 'segments': segs}
    return out


def convert_range(start, end, segments):
    """把 [start, end] 刻度区间按校时段分段累计为秒。
    返回 (秒数|None, 分段明细, 缺口区间, 重叠区间)；缺口或重叠时不产生秒数。"""
    relevant = [s for s in segments if s.start_tick < end and s.end_tick > start]
    overlaps, max_end = [], None
    for s in relevant:
        if max_end is not None and s.start_tick < max_end:
            overlaps.append((max(s.start_tick, start), min(max_end, end)))
        if max_end is None or s.end_tick > max_end:
            max_end = s.end_tick
    if overlaps:
        return None, [], [], overlaps
    gaps, used, seconds, cursor = [], [], 0.0, start
    for s in relevant:
        if s.start_tick > cursor:
            gaps.append((cursor, min(s.start_tick, end)))
        a, b = max(s.start_tick, start), min(s.end_tick, end)
        if b > a:
            ticks = b - a
            sec = ticks * s.seconds_per_tick
            seconds += sec
            used.append({'start': a, 'end': b, 'rate': s.seconds_per_tick, 'ticks': ticks, 'seconds': sec})
        cursor = max(cursor, s.end_tick)
    if cursor < end:
        gaps.append((cursor, end))
    if gaps:
        return None, [], gaps, []
    return seconds, used, [], []


def _evaluate(rec, segments):
    """单条记录换算：前后两段测量都通过才为 converted，否则 blocked 并写明阻塞区间。"""
    detail, seconds = {}, {}
    for key, skey, ekey, cname in MEASURES:
        start, end = getattr(rec, skey), getattr(rec, ekey)
        sec, used, gaps, overlaps = convert_range(start, end, segments)
        where = f'设备 {rec.device} · 开机批号 {rec.boot_no} · {cname}测量 [{_tick(start)}, {_tick(end)}]'
        if overlaps:
            return 'blocked', None, None, {}, where + ' 命中校时依据重叠冲突：' + _fmt_intervals(overlaps)
        if gaps:
            return 'blocked', None, None, {}, where + (' 尚未登记校时依据' if not segments else ' 校时依据存在缺口：' + _fmt_intervals(gaps))
        seconds[key] = sec
        detail[key] = used
    return 'converted', seconds['before'], seconds['after'], detail, ''


def _persist(db, record_id, version, payload):
    """版本守卫：只允许不旧于记录当前依据版本的换算落库，旧换算拒绝覆盖新依据。"""
    stmt = (update(TimingRecord)
            .where(TimingRecord.id == record_id)
            .where(or_(TimingRecord.basis_version.is_(None), TimingRecord.basis_version <= version))
            .values(**payload, basis_version=version, updated_at=time.time()))
    return db.execute(stmt).rowcount == 1


def convert_batch(db, batch, actor='system'):
    """换算一个批次：跳过已按当前依据换算的记录，其余重算；分批提交，
    中断后重入可恢复进度，反复重试不产生副作用。已放行批次不再改动。"""
    stats = {'converted': 0, 'blocked': 0, 'skipped': 0, 'stale_rejected': 0}
    if batch.status == 'released':
        return stats
    rows = db.scalars(select(TimingRecord).where(TimingRecord.batch_id == batch.id).order_by(TimingRecord.row_no)).all()
    basis = _basis_map(db, {(r.device, r.boot_no) for r in rows})
    for i, r in enumerate(rows):
        b = basis[(r.device, r.boot_no)]
        version = b['version'] or 0
        if r.status == 'converted' and (r.basis_version or 0) == version:
            stats['skipped'] += 1
            continue
        status, before, after, detail, error = _evaluate(r, b['segments'])
        payload = {'status': status, 'before_seconds': before, 'after_seconds': after, 'detail': detail, 'error': error}
        if _persist(db, r.id, version, payload):
            stats['converted' if status == 'converted' else 'blocked'] += 1
        else:
            stats['stale_rejected'] += 1
        if i % 100 == 99:
            db.commit()
    _refresh_batch(db, batch)
    db.commit()
    return stats


def _refresh_batch(db, batch):
    counts = dict(db.execute(select(TimingRecord.status, func.count()).where(TimingRecord.batch_id == batch.id).group_by(TimingRecord.status)).all())
    converted, blocked = counts.get('converted', 0), counts.get('blocked', 0)
    if batch.total_count > 0 and converted == batch.total_count:
        status = 'ready'
    elif blocked > 0:
        status = 'blocked'
    else:
        status = 'pending'
    # 条件更新：并发线程的陈旧状态不得覆盖已放行批次
    res = db.execute(update(TimingBatch).where(TimingBatch.id == batch.id, TimingBatch.status != 'released')
                     .values(status=status, converted_count=converted, blocked_count=blocked))
    if res.rowcount == 1:
        batch.status, batch.converted_count, batch.blocked_count = status, converted, blocked
    else:
        db.refresh(batch)


def resume_affected(db, device, boot_no, actor):
    """迟到校时数据补齐（或作废）后，接续换算涉及该设备与开机批号的未放行批次。"""
    ids = db.scalars(select(TimingRecord.batch_id).where(TimingRecord.device == device, TimingRecord.boot_no == boot_no).distinct()).all()
    resumed = []
    for bid in ids:
        batch = db.get(TimingBatch, bid)
        if not batch or batch.status == 'released':
            continue
        stats = convert_batch(db, batch, actor)
        resumed.append({'batch_id': bid, 'status': batch.status, **stats})
    return resumed


def release(db, batch, user):
    """放行：全批记录都按同一套校时依据换算通过，才生成可分析数据批次。
    幂等：已放行直接返回原数据批次，反复重试不新增批次。"""
    if batch.status == 'released' and batch.dataset_id:
        return db.get(Dataset, batch.dataset_id), False
    convert_batch(db, batch, user.email)
    if batch.status == 'released' and batch.dataset_id:
        return db.get(Dataset, batch.dataset_id), False
    if batch.status != 'ready':
        if batch.blocked_count:
            blocked = db.scalars(select(TimingRecord).where(TimingRecord.batch_id == batch.id, TimingRecord.status == 'blocked').order_by(TimingRecord.row_no).limit(3)).all()
            first = '；'.join(f'第 {r.row_no} 行（{r.operator}）：{r.error}' for r in blocked)
            raise HTTPException(409, f'存在 {batch.blocked_count} 条未通过校时换算的测量，阻止放行。{first}')
        raise HTTPException(409, '批次换算尚未完成，请重试')
    rows = db.scalars(select(TimingRecord).where(TimingRecord.batch_id == batch.id).order_by(TimingRecord.row_no)).all()
    basis = _basis_map(db, {(r.device, r.boot_no) for r in rows}, lock=True)
    for r in rows:
        version = basis[(r.device, r.boot_no)]['version'] or 0
        if r.status != 'converted' or (r.basis_version or 0) != version:
            raise HTTPException(409, '校时依据在放行过程中发生更新，整批须采用同一套依据，请重试放行')
    records = [{'operator': r.operator, 'team': r.team, 'before': round(r.before_seconds, 3), 'after': round(r.after_seconds, 3)} for r in rows]
    ds = Dataset(name=_free_dataset_name(db, batch.name), source=batch.source, records=records, checksum=checksum(records), created_at=time.time())
    db.add(ds)
    db.flush()
    snapshot = {f'{device}|{boot_no}': {'device': device, 'boot_no': boot_no, 'version': b['version'],
                                       'segments': [{'start_tick': s.start_tick, 'end_tick': s.end_tick, 'seconds_per_tick': s.seconds_per_tick} for s in b['segments']]}
                for (device, boot_no), b in basis.items()}
    res = db.execute(update(TimingBatch).where(TimingBatch.id == batch.id, TimingBatch.dataset_id.is_(None))
                     .values(status='released', dataset_id=ds.id, basis_snapshot=snapshot, released_at=time.time(), converted_count=batch.total_count, blocked_count=0))
    if res.rowcount != 1:
        raise HTTPException(409, '批次已放行，请勿重复提交')
    batch.status, batch.dataset_id, batch.basis_snapshot, batch.released_at = 'released', ds.id, snapshot, time.time()
    return ds, True


def _free_dataset_name(db, base):
    for name in [base, f'{base} · 校时放行'] + [f'{base} · 校时放行{i}' for i in range(2, 100)]:
        if not db.scalar(select(Dataset).where(Dataset.name == name)):
            return name
    raise HTTPException(409, '同名数据批次过多，请修改待校准批次名称')
