# PROMPT: Generate robust tests for the live detection viewer page, clip discovery, and stream endpoint validation.
# CHANGES MADE: Kept model inference out of unit tests while asserting the browser UI exposes model/clip controls.

from __future__ import annotations

import numpy as np

from app.video_demo import (
    LiveTrack,
    _classify_role,
    _mask_bottom_ratio,
    _parse_uniform_bgr,
    _remember_track_observation,
    _uniform_match_scores,
    _uniform_match_score,
    _update_uniform_evidence,
)


def test_video_demo_page_has_live_detection_controls(client):
    response = client.get("/video-demo")
    html = response.text
    assert response.status_code == 200
    assert "Live Detection Viewer" in html
    assert "storeFilter" in html
    assert "YOLOv8n" in html
    assert "YOLOv8x-seg" in html
    assert "RT-DETR-X" in html
    assert "Mask refinement" in html
    assert "Off - fastest box-only logic" in html
    assert "MobileSAM" in html
    assert "Start live view" in html
    assert "Stop live preview" in html
    assert "notificationButton" in html
    assert "/notifications" in html
    assert "staff-customer interaction" in html
    assert "Staff uniform BGR colors" in html
    assert "Uniform hits for staff" in html
    assert "Static after frames" in html
    assert "Min human bottom Y" in html
    assert "Blur staff cutoff" in html
    assert "Staff area X min" in html
    assert "Staff area bottom Y max" in html
    assert "ignored_static_display" in html
    assert "/video-demo/stream" in html


def test_video_demo_clips_endpoint(client):
    response = client.get("/video-demo/clips")
    assert response.status_code == 200
    assert "clips" in response.json()
    assert "stores" in response.json()


def test_video_demo_missing_clip_returns_404(client):
    response = client.get("/video-demo/stream?clip=missing.mp4")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLIP_NOT_FOUND"


def test_video_demo_state_and_stop_endpoints(client):
    state = client.get("/video-demo/state/test-stream").json()
    assert state["stream_id"] == "test-stream"
    assert state["running"] is False
    stopped = client.post("/video-demo/stop/test-stream").json()
    assert stopped["stream_id"] == "test-stream"
    assert stopped["status"] == "stop_requested"


def test_static_wall_display_is_ignored_after_repeated_static_boxes():
    track = LiveTrack(first_frame=0)
    for _ in range(16):
        _remember_track_observation(track, [100, 70, 160, 150], 0.82, 640, 480)

    role, confidence, reason = _classify_role(
        track,
        frame_width=640,
        frame_height=480,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=3,
    )

    assert role == "ignored_static_display"
    assert confidence >= 0.8
    assert "wall_or_poster" in reason


def test_slow_large_person_is_customer_not_static_display():
    track = LiveTrack(first_frame=0)
    for _ in range(16):
        _remember_track_observation(track, [250, 145, 390, 340], 0.72, 640, 480)

    role, _, reason = _classify_role(
        track,
        frame_width=640,
        frame_height=480,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=3,
    )

    assert role == "customer"
    assert "large_person_relaxed_floor_band" in reason or "floor_contact_customer" in reason


def test_moving_person_is_classified_as_customer_not_staff_by_duration():
    track = LiveTrack(first_frame=0)
    for offset in range(12):
        _remember_track_observation(track, [100 + offset * 4, 190, 180 + offset * 4, 420], 0.79, 640, 480)

    role, _, reason = _classify_role(
        track,
        frame_width=640,
        frame_height=480,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=3,
    )

    assert role == "customer"
    assert reason == "validated_by_track_motion"


def test_uniform_color_evidence_can_classify_staff():
    colors = _parse_uniform_bgr("10,120,200")
    frame = np.zeros((120, 80, 3), dtype=np.uint8)
    frame[25:82, 15:65] = np.array([10, 120, 200], dtype=np.uint8)
    track = LiveTrack(first_frame=0)

    for _ in range(3):
        _remember_track_observation(track, [45, 10, 79, 110], 0.88, 80, 120)
        score = _uniform_match_score(frame, [10, 10, 70, 110], colors)
        _update_uniform_evidence(track, score)

    role, confidence, reason = _classify_role(
        track,
        frame_width=80,
        frame_height=120,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=3,
    )

    assert score >= 0.55
    assert role == "staff"
    assert confidence >= 0.8
    assert "uniform_color_match" in reason


def test_mask_evidence_refines_bottom_and_uniform_sampling():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:, :] = np.array([240, 240, 240], dtype=np.uint8)
    frame[30:60, 45:55] = np.array([20, 90, 180], dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=bool)
    mask[30:86, 45:55] = True

    bottom_y, coverage = _mask_bottom_ratio(mask, [10, 0, 90, 100], 100, 100)
    masked_score = _uniform_match_score(frame, [10, 0, 90, 100], [(20, 90, 180)], mask=mask)
    box_score = _uniform_match_score(frame, [10, 0, 90, 100], [(20, 90, 180)], mask=None)

    assert bottom_y == 85 / 99
    assert coverage > 0
    assert masked_score > box_score


def test_black_uniform_score_separates_dark_staff_from_grey_customer():
    black_frame = np.full((120, 80, 3), 210, dtype=np.uint8)
    black_frame[25:82, 15:65] = np.array([25, 25, 25], dtype=np.uint8)
    grey_frame = np.full((120, 80, 3), 210, dtype=np.uint8)
    grey_frame[25:82, 15:65] = np.array([80, 80, 80], dtype=np.uint8)

    black_score, black_dark_score = _uniform_match_scores(black_frame, [10, 10, 70, 110], [(25, 25, 25)])
    grey_score, grey_dark_score = _uniform_match_scores(grey_frame, [10, 10, 70, 110], [(25, 25, 25)])

    assert black_score >= 0.9
    assert black_dark_score >= 0.9
    assert grey_score < 0.55
    assert grey_dark_score < 0.55


def test_neutral_grey_does_not_match_colored_uniform_hint():
    grey_frame = np.full((120, 80, 3), 210, dtype=np.uint8)
    grey_frame[25:82, 15:65] = np.array([72, 80, 88], dtype=np.uint8)

    score, dark_score = _uniform_match_scores(
        grey_frame,
        [10, 10, 70, 110],
        [(40, 120, 40), (50, 50, 180)],
    )

    assert score < 0.55
    assert dark_score == 0.0


def test_uniform_like_person_outside_staff_area_stays_customer():
    track = LiveTrack(first_frame=0, uniform_hits=4)
    for _ in range(3):
        _remember_track_observation(track, [10, 20, 60, 115], 0.8, 120, 120)

    role, _, reason = _classify_role(
        track,
        frame_width=120,
        frame_height=120,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=3,
        staff_area_x_min=0.75,
    )

    assert role == "customer"
    assert "outside_staff_area" in reason


def test_black_uniform_staff_can_be_foreground():
    track = LiveTrack(first_frame=0, dark_uniform_hits=5, dark_uniform_score=1.0)
    for _ in range(5):
        _remember_track_observation(track, [460, 120, 625, 476], 0.7, 640, 480)

    role, _, reason = _classify_role(
        track,
        frame_width=640,
        frame_height=480,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=4,
        staff_area_x_min=0.66,
        staff_area_bottom_y_max=0.9,
    )

    assert role == "staff"
    assert "black_uniform_hits" in reason


def test_blurred_uniform_person_inside_staff_area_can_be_staff():
    track = LiveTrack(first_frame=0, uniform_hits=4, blur_score=20.0)
    for _ in range(4):
        _remember_track_observation(track, [460, 150, 585, 420], 0.7, 640, 480)

    role, confidence, reason = _classify_role(
        track,
        frame_width=640,
        frame_height=480,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=4,
        staff_area_x_min=0.66,
    )

    assert role == "staff"
    assert confidence >= 0.85
    assert "uniform_color_match" in reason
    assert "blur_real_person" in reason


def test_blurred_uniform_person_outside_staff_area_stays_customer():
    track = LiveTrack(first_frame=0, uniform_hits=10, blur_score=20.0)
    for _ in range(3):
        _remember_track_observation(track, [100, 160, 220, 460], 0.7, 640, 480)

    role, _, reason = _classify_role(
        track,
        frame_width=640,
        frame_height=480,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=3,
    )

    assert role == "customer"
    assert "outside_staff_area" in reason


def test_foreground_uniform_like_customer_stays_customer_even_in_staff_area():
    track = LiveTrack(first_frame=0, uniform_hits=8, blur_score=999.0)
    for _ in range(4):
        _remember_track_observation(track, [460, 120, 625, 476], 0.7, 640, 480)

    role, _, reason = _classify_role(
        track,
        frame_width=640,
        frame_height=480,
        static_after_frames=16,
        static_motion_threshold=0.006,
        staff_uniform_hits=4,
        staff_area_x_min=0.66,
        staff_area_bottom_y_max=0.9,
    )

    assert role == "customer"
    assert "foreground_customer" in reason
