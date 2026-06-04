from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

import requests


def _read_stream_bytes(response: requests.Response, *, min_bytes: int) -> int:
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total >= min_bytes or b"\xff\xd8" in chunk:
            return total
    return total


def smoke(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.url.rstrip("/")
    clips_response = requests.get(f"{base_url}/video-demo/clips", timeout=10)
    clips_response.raise_for_status()
    clips = clips_response.json().get("clips") or []
    if not clips:
        raise RuntimeError("No clips are available from /video-demo/clips.")

    clip = clips[0]
    stream_id = f"setup-smoke-{uuid.uuid4().hex}"
    params = {
        "clip": clip["id"],
        "store_id": clip.get("store_id") or "",
        "model": args.model,
        "mask_refiner": "off",
        "conf": args.conf,
        "imgsz": args.imgsz,
        "stride": args.stride,
        "stream_fps": args.stream_fps,
        "stream_id": stream_id,
    }
    response = None
    try:
        response = requests.get(
            f"{base_url}/video-demo/stream",
            params=params,
            stream=True,
            timeout=(10, args.read_timeout),
        )
        response.raise_for_status()
        byte_count = _read_stream_bytes(response, min_bytes=args.min_bytes)
        if byte_count < args.min_bytes:
            raise RuntimeError(f"Stream returned only {byte_count} bytes; expected at least {args.min_bytes}.")
        state = requests.get(f"{base_url}/video-demo/state/{stream_id}", timeout=10).json()
        if str(state.get("status", "")).startswith("stream_error"):
            raise RuntimeError(f"Stream entered error state: {state.get('status')}")
        return {
            "ok": True,
            "clip": clip["id"],
            "store_id": clip.get("store_id"),
            "stream_id": stream_id,
            "bytes": byte_count,
            "status": state.get("status"),
            "tracker_backend": state.get("tracker_backend"),
            "tracking_warning": state.get("tracking_warning"),
        }
    finally:
        if response is not None:
            response.close()
        try:
            requests.post(f"{base_url}/video-demo/stop/{stream_id}", timeout=10)
        except requests.RequestException:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the browser-facing MJPEG video-demo stream.")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--stride", type=int, default=30)
    parser.add_argument("--stream-fps", type=float, default=1.0)
    parser.add_argument("--read-timeout", type=float, default=90.0)
    parser.add_argument("--min-bytes", type=int, default=512)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = smoke(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
