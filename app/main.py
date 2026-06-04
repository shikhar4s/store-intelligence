from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.anomalies import compute_anomalies
from app.config import get_settings
from app.dashboard import render_dashboard
from app.database import get_db, get_engine, init_db
from app.errors import (
    ServiceUnavailableError,
    http_exception_handler,
    service_unavailable_handler,
    sqlalchemy_error_handler,
    unhandled_exception_handler,
)
from app.funnel import compute_funnel
from app.health import health_status
from app.heatmap import compute_heatmap
from app.ingestion import count_events_payload, ingest_payload
from app.logging_config import configure_logging
from app.metrics import compute_metrics
from app.notifications import list_notifications
from app.pos import ingest_pos_payload
from app.stores import list_stores
from app.video_demo import (
    DEFAULT_BLUR_STAFF_MAX_VARIANCE,
    DEFAULT_MIN_HUMAN_BOTTOM_Y,
    DEFAULT_STAFF_AREA_BOTTOM_Y_MAX,
    DEFAULT_STAFF_AREA_X_MIN,
    DEFAULT_STAFF_UNIFORM_HITS,
    DEFAULT_STATIC_AFTER_FRAMES,
    DEFAULT_STATIC_APPEARANCE_THRESHOLD,
    DEFAULT_STATIC_MOTION_THRESHOLD,
    DEFAULT_UNIFORM_BGR,
    get_live_state,
    list_video_clips,
    list_video_stores,
    mjpeg_detection_stream,
    render_video_demo,
    resolve_clip,
    stop_live_stream,
)


logger = logging.getLogger("store_intelligence.request")


def _store_id_from_path(request: Request) -> Optional[str]:
    value = request.path_params.get("store_id")
    return str(value) if value else None


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        if settings.seed_demo_on_startup:
            from app.bootstrap import seed_demo_data_if_needed

            with Session(get_engine()) as db:
                seed_demo_data_if_needed(db)
        yield

    api = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

    @api.middleware("http")
    async def request_logging(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or str(uuid4())
        request.state.trace_id = trace_id
        request.state.event_count = None
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = getattr(response, "status_code", 500)
            if response is not None:
                response.headers["X-Trace-Id"] = trace_id
            logger.info(
                "request_complete",
                extra={
                    "trace_id": trace_id,
                    "endpoint": request.url.path,
                    "method": request.method,
                    "store_id": _store_id_from_path(request),
                    "latency_ms": latency_ms,
                    "event_count": request.state.event_count,
                    "status_code": status_code,
                },
            )

    api.add_exception_handler(ServiceUnavailableError, service_unavailable_handler)
    api.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    api.add_exception_handler(StarletteHTTPException, http_exception_handler)
    api.add_exception_handler(Exception, unhandled_exception_handler)

    @api.post("/events/ingest")
    async def ingest_events(request: Request, db: Session = Depends(get_db)):
        payload: Any = await request.json()
        request.state.event_count = count_events_payload(payload)
        return ingest_payload(db, payload, trace_id=getattr(request.state, "trace_id", None))

    @api.post("/pos/ingest")
    async def ingest_pos(request: Request, db: Session = Depends(get_db)):
        payload: Any = await request.json()
        return ingest_pos_payload(db, payload)

    @api.get("/stores")
    def stores(db: Session = Depends(get_db)):
        return list_stores(db)

    @api.get("/stores/{store_id}/metrics")
    def metrics(
        store_id: str,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_metrics(db, store_id, date=date, start=start, end=end)

    @api.get("/metrics")
    def metrics_alias(
        store_id: str = settings.default_store_id,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_metrics(db, store_id, date=date, start=start, end=end)

    @api.get("/stores/{store_id}/funnel")
    def funnel(
        store_id: str,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_funnel(db, store_id, date=date, start=start, end=end)

    @api.get("/funnel")
    def funnel_alias(
        store_id: str = settings.default_store_id,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_funnel(db, store_id, date=date, start=start, end=end)

    @api.get("/stores/{store_id}/heatmap")
    def heatmap(
        store_id: str,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_heatmap(db, store_id, date=date, start=start, end=end)

    @api.get("/heatmap")
    def heatmap_alias(
        store_id: str = settings.default_store_id,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_heatmap(db, store_id, date=date, start=start, end=end)

    @api.get("/stores/{store_id}/anomalies")
    def anomalies(
        store_id: str,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_anomalies(db, store_id, date=date, start=start, end=end)

    @api.get("/anomalies")
    def anomalies_alias(
        store_id: str = settings.default_store_id,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        return compute_anomalies(db, store_id, date=date, start=start, end=end)

    @api.get("/health")
    def health(db: Session = Depends(get_db)):
        return health_status(db)

    @api.get("/notifications")
    def notifications(db: Session = Depends(get_db)):
        return list_notifications(db)

    @api.get("/dashboard", response_class=HTMLResponse)
    def dashboard(store_id: str = settings.default_store_id):
        return HTMLResponse(render_dashboard(store_id))

    @api.get("/video-demo", response_class=HTMLResponse)
    def video_demo():
        return HTMLResponse(render_video_demo())

    @api.get("/video-demo/clips")
    def video_demo_clips():
        clips = list_video_clips()
        return {"clips": clips, "stores": list_video_stores(clips)}

    @api.get("/video-demo/state/{stream_id}")
    def video_demo_state(stream_id: str):
        return get_live_state(stream_id)

    @api.post("/video-demo/stop/{stream_id}")
    def video_demo_stop(stream_id: str):
        return stop_live_stream(stream_id)

    @api.get("/video-demo/stream")
    def video_demo_stream(
        clip: str,
        store_id: Optional[str] = None,
        model: str = "yolo11n.pt",
        mask_refiner: str = "off",
        conf: float = 0.25,
        imgsz: int = 960,
        stride: int = 5,
        stream_fps: float = 4.0,
        device: Optional[str] = None,
        stream_id: str = "default",
        uniform_bgr: str = DEFAULT_UNIFORM_BGR,
        staff_uniform_hits: int = DEFAULT_STAFF_UNIFORM_HITS,
        static_after_frames: int = DEFAULT_STATIC_AFTER_FRAMES,
        static_motion_threshold: float = DEFAULT_STATIC_MOTION_THRESHOLD,
        static_appearance_threshold: float = DEFAULT_STATIC_APPEARANCE_THRESHOLD,
        min_human_bottom_y: float = DEFAULT_MIN_HUMAN_BOTTOM_Y,
        blur_staff_max_variance: float = DEFAULT_BLUR_STAFF_MAX_VARIANCE,
        staff_area_x_min: float = DEFAULT_STAFF_AREA_X_MIN,
        staff_area_bottom_y_max: float = DEFAULT_STAFF_AREA_BOTTOM_Y_MAX,
        interaction_distance: float = 0.22,
        interaction_frames: int = 3,
    ):
        clip_path = resolve_clip(clip)
        return StreamingResponse(
            mjpeg_detection_stream(
                clip_path=clip_path,
                store_id=store_id,
                model_name=model,
                mask_refiner=mask_refiner,
                conf=conf,
                imgsz=imgsz,
                stride=stride,
                stream_fps=stream_fps,
                device=device,
                stream_id=stream_id,
                uniform_bgr=uniform_bgr,
                staff_uniform_hits=staff_uniform_hits,
                static_after_frames=static_after_frames,
                static_motion_threshold=static_motion_threshold,
                static_appearance_threshold=static_appearance_threshold,
                min_human_bottom_y=min_human_bottom_y,
                blur_staff_max_variance=blur_staff_max_variance,
                staff_area_x_min=staff_area_x_min,
                staff_area_bottom_y_max=staff_area_bottom_y_max,
                interaction_distance=interaction_distance,
                interaction_frames=interaction_frames,
            ),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    return api


app = create_app()
