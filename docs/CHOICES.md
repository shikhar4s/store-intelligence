# Choices

## 1. Detection Model and Tracker

Options considered: RT-DETR-L/X, YOLO11n/s/m/l/x, YOLOv8n/s/m/l/x, retail-specific CCTV models, ByteTrack, BoT-SORT, DeepSORT/StrongSORT, and optional OSNet/torchreid ReID.

AI first suggested a lightweight YOLO default for acceptance reliability. After revisiting the goal of highest practical accuracy, I changed the default detector to `rtdetr-x.pt` because Ultralytics documents RT-DETR-X at 54.8 AP on COCO val2017, slightly above YOLO11x at 54.7 and YOLOv8x at 53.9. The pipeline still supports YOLO11/YOLOv8 models, and `yolo11x.pt` or `yolov8x.pt` are the recommended fallback choices when built-in tracker IDs are more important than the marginal AP gain.

The default detection settings now use person class only, `--sample-fps 5`, `--confidence 0.10`, and `--imgsz 960`. This is intentionally accuracy-biased for 1080p CCTV, especially for smaller or partially occluded people. It is heavier than the original nano-model setting, so production deployments should benchmark on the target RTX 4060 and step down to `yolo11s.pt` or `yolov8s.pt` if throughput is unacceptable.

COCO person detectors can fire on printed wall posters because the image still looks like a person. The live viewer and offline event pipeline therefore add a camera-calibrated validation layer above the detector: new tracks remain `customer_candidate`, detections whose mask/box bottom is above the configured floor-contact band are marked `ignored_static_display`, blur is treated as real-person evidence rather than a hard staff/customer override, and repeated torso color matches against configured uniform hints validate `staff`. In the CAM 1 clip the apparent staff uniform is black, so black hints use a separate strict dark-pixel fraction instead of broad BGR distance; this prevents grey blurred customer clothing from being treated as staff while still allowing foreground black-uniform staff. I chose this conservative role layer over duration-only staff labeling because duration caused real customers to be mislabeled as staff.

For the live visual demo I added segmentation and SAM-style refinement as optional accuracy layers, not default dependencies. The default live model is now `yolo11n.pt` with Mask refinement `off` because it starts quickly and avoids extra downloads while the user is checking camera setup. If masks help a specific camera, the UI can switch to `auto` for native segmentation-model masks or to `mobile_sam.pt`, `FastSAM-s.pt`, or `sam_b.pt` for box-prompted refinement. These refiners are not staff/customer classifiers; they improve mask quality, while the final role decision still comes from floor-contact, uniform evidence, blur, and optional staff-area controls. Weights download lazily and remain untracked by git.

After testing against the store footage, I made the live role layer favor customer recall over overzealous static filtering. Static-display suppression now waits longer, uses a lower motion threshold, and does not override person-sized mask/box evidence. This means a slow customer browsing a shelf is counted as customer; only small high-wall-like detections with persistent near-zero motion are ignored as posters.

License notes: Ultralytics models/package are AGPL-3.0 unless an Enterprise license is used. ByteTrack and BoT-SORT reference repositories are MIT. For a commercial deployment, the license choice must be reviewed before embedding Ultralytics in a closed product.

Fallback if the model cannot load: `pipeline.detect` emits deterministic, low-confidence fallback events from discovered video files and resource timestamps. This does not pretend to be accurate CV. It ensures the repo remains runnable and makes fallback status visible in metadata.

## 2. Event Schema Design

The schema is designed to support all challenge endpoints without coupling the API to detector internals. `ENTRY`, `EXIT`, and `REENTRY` support unique visitor counting and reentry deduplication. `ZONE_ENTER`, `ZONE_EXIT`, and `ZONE_DWELL` support dwell and heatmap. `BILLING_QUEUE_JOIN` and `BILLING_QUEUE_ABANDON` support queue depth and abandonment. POS conversion is computed outside the event stream by joining billing touches to POS timestamps.

`confidence` is kept on every event because weak detections still carry signal. The API uses it to set `data_confidence` rather than dropping rows silently. `is_staff` is stored per event so staff can be excluded from every metric consistently even if a later CV pass improves staff classification. `metadata.session_seq` gives ordered context inside a visitor session. `metadata.queue_depth` makes queue anomalies computable without reconstructing every frame, and `metadata.sku_zone` lets layout names survive even if the zone id is operational.

AI suggested a richer schema with track bounding boxes and model debug tensors. I rejected that for the public API because those fields would increase payload size and expose CV implementation details. The current schema keeps operational analytics stable while leaving room for optional metadata.

## 3. API and Storage Architecture

Options considered: SQLite, Postgres, in-memory event stores, and precomputed metric tables. I chose FastAPI, Pydantic validation, SQLAlchemy, and SQLite WAL by default.

SQLite is not the final answer for 40 live stores, but it is the right default for this challenge. It lets `docker compose up` start the API without another service and still gives durable storage, indexes, unique constraints, and simple local inspection. SQLAlchemy keeps the route to Postgres open. For production, I would move events to Postgres partitioned by store/date and add incremental rollups for current queue depth and session funnel stages.

Idempotency is enforced by a unique `event_id` and explicit duplicate counting before insert. Partial success is handled at the validation layer, so one malformed event does not poison a full batch. Real-time metrics are computed from stored events on each request. That is acceptable for the challenge data size and safer than caching incorrect state during development. The scaling tradeoff is documented: when event volume grows, the first change should be rollup tables or materialized views rather than rewriting the API contract.
