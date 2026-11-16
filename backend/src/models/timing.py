from sqlalchemy import String, JSON, Double, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class CalibrationBasis(Base):
    """每台设备每个开机批号一套校时依据；version 随登记/作废单调递增。"""
    __tablename__ = 'calibration_basis'
    id: Mapped[int] = mapped_column(primary_key=True)
    device: Mapped[str] = mapped_column(String(80))
    boot_no: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (UniqueConstraint('device', 'boot_no', name='uq_basis_device_boot'),)
class CalibrationSegment(Base):
    """校时依据的一段刻度区间：该区间内每刻度折合固定秒数。"""
    __tablename__ = 'calibration_segments'
    id: Mapped[int] = mapped_column(primary_key=True)
    basis_id: Mapped[int] = mapped_column(ForeignKey('calibration_basis.id'))
    device: Mapped[str] = mapped_column(String(80))
    boot_no: Mapped[str] = mapped_column(String(80))
    start_tick: Mapped[float] = mapped_column(Double)
    end_tick: Mapped[float] = mapped_column(Double)
    seconds_per_tick: Mapped[float] = mapped_column(Double)
    version: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(150), default='')
    created_at: Mapped[float] = mapped_column(Double)
class TimingBatch(Base):
    """设备测时待校准批次；全批换算通过后才放行生成可分析数据批次。"""
    __tablename__ = 'timing_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    converted_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    basis_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(150), default='')
    created_at: Mapped[float] = mapped_column(Double)
    released_at: Mapped[float | None] = mapped_column(Double, nullable=True)
class TimingRecord(Base):
    """一条配对测时的原始刻度：设备、开机批号与前后测量起止刻度。"""
    __tablename__ = 'timing_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('timing_batches.id'))
    row_no: Mapped[int] = mapped_column(Integer)
    operator: Mapped[str] = mapped_column(String(120))
    team: Mapped[str] = mapped_column(String(80))
    device: Mapped[str] = mapped_column(String(80))
    boot_no: Mapped[str] = mapped_column(String(80))
    before_start: Mapped[float] = mapped_column(Double)
    before_end: Mapped[float] = mapped_column(Double)
    after_start: Mapped[float] = mapped_column(Double)
    after_end: Mapped[float] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    before_seconds: Mapped[float | None] = mapped_column(Double, nullable=True)
    after_seconds: Mapped[float | None] = mapped_column(Double, nullable=True)
    basis_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(500), default='')
    updated_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (UniqueConstraint('batch_id', 'row_no', name='uq_timing_batch_row'),)
