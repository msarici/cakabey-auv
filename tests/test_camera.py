"""Hardware-free camera backend selection and failed-open cleanup."""
from unittest.mock import Mock
import camera


def test_csi_selects_argus_backend_sensor_and_fps(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = True
    factory = Mock(return_value=capture)
    monkeypatch.setattr(camera.cv2, 'VideoCapture', factory)
    cam = camera.Camera(source='csi', device_id=1, fps=30)
    assert cam.open()
    pipeline, backend = factory.call_args.args
    assert 'nvarguscamerasrc sensor-id=1' in pipeline
    assert 'framerate=30/1' in pipeline
    assert 'max-buffers=1' in pipeline
    assert backend == camera.cv2.CAP_GSTREAMER
    cam.close()
    capture.release.assert_called_once()


def test_failed_open_releases_capture_without_fallback(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = False
    monkeypatch.setattr(camera.cv2, 'VideoCapture', Mock(return_value=capture))
    cam = camera.Camera(source='csi')
    assert not cam.open()
    assert cam.source == 'csi'
    capture.release.assert_called_once()


def test_explicit_camera_fallback_still_works(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = False
    monkeypatch.setattr(camera.cv2, 'VideoCapture', Mock(return_value=capture))
    cam = camera.Camera(source='csi', allow_test_fallback=True)
    assert cam.open()
    assert cam.source == 'test'
    assert cam.read().shape == (480, 640, 3)
    capture.release.assert_called_once()
