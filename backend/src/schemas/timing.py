from pydantic import BaseModel, Field
class TimingBatchInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source: str = Field(default='manual.json', max_length=200)
    records: list[dict] = Field(min_length=1, max_length=5000)
class SegmentInput(BaseModel):
    start_tick: float
    end_tick: float
    seconds_per_tick: float
class SegmentSetInput(BaseModel):
    device: str = Field(min_length=1, max_length=80)
    boot_no: str = Field(min_length=1, max_length=80)
    segments: list[SegmentInput] = Field(min_length=1, max_length=200)
