"""scripts/evidence_package.py gathers hashes, timing and truth without inventing any."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evidence_package",
                                              ROOT / "scripts" / "evidence_package.py")
ep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ep)


def test_package_from_artifacts(tmp_path):
    art = tmp_path / "artifacts"
    art.mkdir()
    video = tmp_path / "in.mp4"
    video.write_bytes(b"not really a video")
    vh = hashlib.sha256(video.read_bytes()).hexdigest()
    (art / "manifest.json").write_text(json.dumps({"video_sha256": vh,
                                                   "params": {"preset": "balanced"}}))
    (art / "timing.json").write_text(json.dumps({"wall_s": 732.0, "video_s": 678.0,
                                                 "wall_over_video": 1.08,
                                                 "stages_s": {"sfm": 100.0}}))
    (art / "georeference.json").write_text(json.dumps({
        "georeferenced": True, "projected_crs": "EPSG:32650",
        "vertical_datum": "ellipsoidal", "scale_source": "rtk"}))
    (art / "point_cloud.las").write_bytes(b"LASF")
    pkg = ep.build(art, video)
    assert pkg["input_video"]["matches_manifest"] is True
    assert pkg["timings"]["wall_over_video"] == 1.08
    assert pkg["georeference"]["projected_crs"] == "EPSG:32650"
    assert pkg["outputs"]["point_cloud.las"]["sha256"] == hashlib.sha256(b"LASF").hexdigest()
    assert pkg["truth"]["source"] is None and "not established" in pkg["truth"]["note"]
    md = ep.to_markdown(pkg)
    assert "matches" in md and "EPSG:32650" in md


def test_wrong_video_is_flagged(tmp_path):
    art = tmp_path / "a"
    art.mkdir()
    (art / "manifest.json").write_text(json.dumps({"video_sha256": "0" * 64}))
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    assert ep.main([str(art), "--video", str(v)]) == 2
    assert (art / "evidence_package.md").exists()


def test_accuracy_report_is_carried(tmp_path):
    art = tmp_path / "a"
    art.mkdir()
    (art / "accuracy.json").write_text(json.dumps({
        "truth_source": "DGPS survey", "n_gcp": 4, "n_check": 6,
        "headline": {"text": "RMSE horizontal 0.1 m"}, "asprs": {"sample_sufficient": False}}))
    pkg = ep.build(art)
    assert pkg["truth"]["source"] == "DGPS survey"
    assert "GCPs" in pkg["accuracy_policy"]
