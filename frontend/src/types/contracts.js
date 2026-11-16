/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,name:string,status:string,total_count:number,converted_count:number,blocked_count:number,dataset_id:number|null,basis_snapshot:Object}} TimingBatch */
/** @typedef {{id:number,row_no:number,operator:string,team:string,device:string,boot_no:string,before_start:number,before_end:number,after_start:number,after_end:number,status:string,before_seconds:number|null,after_seconds:number|null,basis_version:number|null,detail:Object,error:string}} TimingRecord */
/** @typedef {{id:number,device:string,boot_no:string,version:number,updated_at:number,conflict:boolean,segments:Array}} CalibrationBasis */
export {};
