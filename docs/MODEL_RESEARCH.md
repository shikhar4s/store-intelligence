# Model Research

Research date/time: 2026-05-31, Asia/Kolkata.

This project has two goals that pull in opposite directions: use the most accurate practical person detector for CCTV review, and keep the API runnable without GPU or CV dependencies. I checked current public documentation and model pages, then implemented a pluggable detector that prefers RT-DETR-X for high-accuracy runs, supports YOLO11/YOLOv8 alternatives, and falls back gracefully when the optional CV stack is absent.

## Sources Checked

- Ultralytics YOLO11 docs: https://docs.ultralytics.com/models/yolo11/
- Ultralytics YOLOv8 docs: https://docs.ultralytics.com/models/yolov8/
- Ultralytics tracking docs: https://docs.ultralytics.com/modes/track/
- Ultralytics RT-DETR docs: https://docs.ultralytics.com/models/rtdetr/
- Ultralytics segmentation task docs: https://docs.ultralytics.com/tasks/segment/
- Ultralytics SAM docs: https://docs.ultralytics.com/models/sam/
- Hugging Face Ultralytics/YOLO11 model card: https://huggingface.co/Ultralytics/YOLO11
- ByteTrack repository: https://github.com/FoundationVision/ByteTrack
- BoT-SORT repository: https://github.com/NirAharon/BoT-SORT
- Torchreid / OSNet repository: https://github.com/KaiyangZhou/deep-person-reid

## Options Considered

| Candidate | Memory/practicality | CPU fallback | Install complexity | License notes | Retail CCTV fit |
| --- | --- | --- | --- | --- | --- |
| YOLO11n | 2.6M params and 6.5B FLOPs per Ultralytics/HF tables; small enough for sampled 1080p CCTV and RTX 4060 | Works on CPU, especially with `--sample-fps 3-5` | `pip install ultralytics`; first model load downloads weights | AGPL-3.0 or Enterprise from Ultralytics | Fast fallback: COCO person class, tracking integration, strong speed/accuracy trade-off |
| YOLO11s | 9.4M params and 21.5B FLOPs; better mAP than nano | CPU possible but slower | Same as YOLO11n | AGPL-3.0 or Enterprise | Good upgrade when GPU is available and accuracy matters more than speed |
| YOLOv8n | Mature, common baseline; similar operational profile to YOLO11n | Good CPU path | Same Ultralytics stack | AGPL-3.0 or Enterprise | Good legacy fallback if newer weights cannot be downloaded |
| YOLOv8s/m/l/x | YOLOv8x reaches 53.9 COCO mAP at 640 in Ultralytics docs; larger variants are slower | CPU possible but slow for x/l | Same | AGPL-3.0 or Enterprise | Useful when the user explicitly wants YOLOv8; not highest checked AP |
| YOLOv8n-seg / YOLOv8x-seg | Adds person instance masks. Nano is fast; x-seg is heavier but improves floor-contact and uniform evidence in the live viewer | Nano works on CPU; x-seg is GPU-preferred | Same package; weights download lazily and are gitignored | AGPL-3.0 or Enterprise | Chosen for live role debugging because masks reduce background/shelf contamination |
| SAM / MobileSAM / FastSAM | Box-prompted mask refinement can sharpen person boundaries after a detector proposes boxes | MobileSAM/FastSAM are practical; SAM vit_b is heavier | Same Ultralytics API, but extra weights | License must be reviewed for commercial use; Meta SAM family has separate terms | Optional live-preview refinement, not the primary classifier |
| YOLO11x | 54.7 COCO mAP at 640 in Ultralytics docs, fewer params/FLOPs than YOLOv8x | CPU slow, GPU recommended | Same | AGPL-3.0 or Enterprise | Best YOLO-family accuracy option checked |
| RT-DETR-X | 54.8 AP on COCO val2017 per Ultralytics docs; RT-DETR-L is 53.0 AP | GPU recommended; CPU fallback is not attractive | Same package, but no built-in tracker IDs in this implementation | AGPL-3.0 wrapper plus upstream citation/license review | Chosen high-accuracy detector because it edges YOLO11x on official AP |
| Retail/CCTV-specific HF models | Some exist, but many are forks, lack stable APIs, or have unclear licensing/data provenance | Varies | Higher integration risk | Often unclear | Not chosen for challenge reliability |

## Tracking Options

| Tracker | Pros | Cons | Decision |
| --- | --- | --- | --- |
| ByteTrack | Designed to associate low-score detections instead of dropping them, which matches the challenge requirement to degrade gracefully under occlusion. Ultralytics exposes it as `bytetrack.yaml`. | Appearance-free, so long occlusions can still fragment IDs. | Fast YOLO fallback. |
| BoT-SORT | Default in Ultralytics tracking docs and adds stronger association ideas. MIT reference repo. | More moving parts; can be slower and can need ReID tuning. | Default for YOLO models when using accuracy settings. |
| DeepSORT / StrongSORT | Familiar appearance-assisted tracking. | More dependencies and model weights; heavier for quick challenge acceptance. | Not included in default path. |

## Re-ID and Staff Handling

I did not make torchreid/OSNet a required dependency. Torchreid is useful and has pretrained ReID models, but it adds PyTorch model downloads and another failure mode. The implemented default is:

- Short-term visitor identity from tracker IDs.
- Cross-camera and reentry hints from time, trajectory, and a lightweight feature hash placeholder.
- Staff/display heuristics from long-duration multi-zone presence, repeated entry/exit patterns, configurable uniform color hints in `configs/cameras.example.yaml`, floor-contact calibration that rejects wall/poster detections above the walkable band, segmentation-mask torso sampling, optional SAM/FastSAM mask refinement, a stricter dark-pixel staff-uniform score for black clothing, and a blur signal that confirms a real anonymized person without overriding stronger uniform evidence.

This is honest about its limits but keeps the project runnable under the challenge constraints.

## Final Choice

Default detector: `rtdetr-x.pt` through Ultralytics RTDETR, person class only, with `conf=0.10`, `imgsz=960`, frame skipping via `--sample-fps`, and normalized zones/entry lines.

Default tracker: RT-DETR uses a local centroid association layer because the high-accuracy detection path is prediction-first. YOLO fallback models use BoT-SORT by default (`botsort.yaml`).

Live preview detector: `yolo11n.pt` by default with mask refinement off for speed and predictable startup. The live viewer can switch to YOLO segmentation models for native masks or to `mobile_sam.pt`, `FastSAM-s.pt`, and `sam_b.pt` as optional box-prompted mask refiners when a specific camera benefits from mask-quality improvements. Weights are downloaded lazily by Ultralytics into ignored model files/cache.

Fallback detector: deterministic low-confidence event generator based on discovered video files, layout/POS timestamps, and camera mapping when Ultralytics/OpenCV/model weights are unavailable. This fallback is not a claim of high CV accuracy. Its purpose is acceptance robustness: the pipeline still emits schema-valid events that vary with input files and preserve low confidence/fallback metadata.

## Why Not Heavier Alternatives

RT-DETR-X is heavier than YOLO11n/YOLOv8n, but it is the highest official AP option checked that is still exposed through the same practical Ultralytics stack. If it fails on a 6 GB RAM/RTX 4060 environment, use `yolo11x.pt` or `yolov8x.pt` for high accuracy with built-in tracking, then step down to `yolo11s.pt` or `yolov8s.pt` for throughput.

## How to Swap Later

Use:

```bash
python -m pipeline.detect --input datasets/cctv_footage --output outputs/events.jsonl --model rtdetr-x.pt --sample-fps 5 --confidence 0.10 --imgsz 960 --device 0
python -m pipeline.detect --input datasets/cctv_footage --output outputs/events.jsonl --model yolo11x.pt --tracker botsort.yaml --sample-fps 5 --confidence 0.10 --imgsz 960 --device 0
```

For a custom model, pass a local `.pt` path to `--model`. For production, calibrate `configs/cameras.example.yaml` from camera screenshots, then copy those normalized lines/polygons into `configs/store_layout.generated.json`.
