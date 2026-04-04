from pathlib import Path
import cv2
import numpy as np
import pytest

FIXTURE_VIDEO = Path(__file__).parent / "fixtures" / "video_fixture.mov"


@pytest.fixture(scope="session")
def fixture_video_path() -> Path:
    if not FIXTURE_VIDEO.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE_VIDEO}")
    return FIXTURE_VIDEO


@pytest.fixture(scope="session")
def two_frames(fixture_video_path) -> tuple[np.ndarray, np.ndarray]:
    """Load two consecutive BGR frames from the fixture video."""
    cap = cv2.VideoCapture(str(fixture_video_path))
    ret1, f1 = cap.read()
    ret2, f2 = cap.read()
    cap.release()
    assert ret1 and ret2, "Could not read two frames from fixture video"
    return f1, f2
