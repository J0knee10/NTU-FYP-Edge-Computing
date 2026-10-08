import numpy as np

from fanlog.datasets import UCI_CSV, load_uci_accelerometer
from fanlog.recording import session_recording, uci_recordings
from fanlog.session import convert
from test_session import _write_session


def _write_uci(tmp_path):
    lines = ["wconfid,pctid,x,y,z"]
    for conf in (1, 2, 3):
        for pct in (20, 25):
            for i in range(4):
                lines.append(f"{conf},{pct},{conf}.0,{pct}.0,{i}.0")
    (tmp_path / "accelerometer (1).csv").write_text("\n".join(lines) + "\n")
    return tmp_path


def test_load_uci_groups_clips_and_renames_archive_csv(tmp_path):
    clips = load_uci_accelerometer(_write_uci(tmp_path))

    assert (tmp_path / UCI_CSV).exists()
    assert sorted(clips) == [
        ("neighbouring", 20), ("neighbouring", 25),
        ("opposite", 20), ("opposite", 25),
        ("perpendicular", 20), ("perpendicular", 25),
    ]
    clip = clips[("perpendicular", 25)]
    assert clip.shape == (4, 3)
    np.testing.assert_array_equal(clip[:, 0], 2.0)
    np.testing.assert_array_equal(clip[:, 2], [0, 1, 2, 3])


def test_uci_recordings(tmp_path):
    recs = {r.name: r for r in uci_recordings(_write_uci(tmp_path))}

    assert len(recs) == 6
    r = recs["opposite_25"]
    assert (r.source, r.rate_hz, r.condition, r.severity, r.speed_pct) == ("uci", 50.0, "opposite", "0", 25.0)
    assert recs["neighbouring_20"].severity == "2"


def test_session_recording(tmp_path):
    _write_session(tmp_path)
    convert(tmp_path)

    r = session_recording(tmp_path)

    assert r.source == "own"
    assert abs(r.rate_hz - 952.0) < 1.0
    assert r.acc_g.shape == (60 * 32, 3)
    assert np.abs(r.acc_g).max() <= 500 * 0.000122 + 1e-12
