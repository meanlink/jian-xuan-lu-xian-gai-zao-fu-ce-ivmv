import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def timing_batch_dict(b):
    return {k:getattr(b,k) for k in ['id','name','source','status','total_count','converted_count','blocked_count','dataset_id','basis_snapshot','created_at','released_at']}
def timing_record_dict(r):
    return {k:getattr(r,k) for k in ['id','batch_id','row_no','operator','team','device','boot_no','before_start','before_end','after_start','after_end','status','before_seconds','after_seconds','basis_version','detail','error','updated_at']}
def basis_dict(b,segments):
    conflict=set()
    ordered=sorted(segments,key=lambda s:(s.start_tick,s.id))
    max_end,max_seg=None,None
    for s in ordered:
        if max_end is not None and s.start_tick<max_end:
            conflict.add(s.id)
            if max_seg:conflict.add(max_seg.id)
        if max_end is None or s.end_tick>max_end:
            max_end,max_seg=s.end_tick,s
    return {'id':b.id,'device':b.device,'boot_no':b.boot_no,'version':b.version,'updated_at':b.updated_at,'conflict':bool(conflict),
            'segments':[{'id':s.id,'start_tick':s.start_tick,'end_tick':s.end_tick,'seconds_per_tick':s.seconds_per_tick,'version':s.version,'created_by':s.created_by,'created_at':s.created_at,'conflict':s.id in conflict} for s in ordered]}
