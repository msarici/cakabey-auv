"""Actual configured CV pipeline; synthetic evidence, not field calibration."""
from pathlib import Path
import cv2
import numpy as np
import pytest
import yaml
from anomaly_detector import AnomalyDetector
from evaluator_anomaly import AnomalyDataset
from evaluator_hsv import HSVEvaluator
from pipe_detector import PipeDetector


@pytest.fixture(scope='module')
def pipeline():
    cfg = yaml.safe_load((Path(__file__).parents[1] / 'config.yaml').read_text())
    return (PipeDetector(**cfg['detector']),
            AnomalyDetector(**{k: v for k, v in cfg['anomaly'].items() if k != 'enabled'}))


def transform(frame, angle):
    return cv2.warpAffine(frame, cv2.getRotationMatrix2D((320, 240), angle, 1),
                          (640, 480), borderValue=(55, 45, 25))


@pytest.mark.parametrize('seed', [0, 1, 7, 42, 99])
@pytest.mark.parametrize('angle', [0, 30, 90, -30])
@pytest.mark.parametrize('label', AnomalyDataset.LABELS)
def test_configured_pipeline_detects_fixture_without_spurious_labels(pipeline, seed, angle, label):
    pipe, anomaly = pipeline
    frame, _ = AnomalyDataset(seed=seed).make(label)
    frame = transform(frame, angle)
    detection = pipe.detect(frame)
    assert detection['found']
    labels = {result['type'] for result in anomaly.detect(frame, detection)}
    assert labels == (set() if label == 'clean' else {label})


@pytest.mark.parametrize('angle', [0, 30, 90])
def test_off_axis_or_far_distractors_do_not_join_inspection_region(pipeline, angle):
    pipe, anomaly = pipeline
    frame, _ = AnomalyDataset(seed=17).make_clean_with_distractor()
    frame = transform(frame, angle)
    detection = pipe.detect(frame)
    assert anomaly.detect(frame, detection) == []
    assert detection['anomaly_bbox'] == detection['bbox']


def test_break_inspection_includes_both_fragments_without_changing_control_target(pipeline):
    pipe, anomaly = pipeline
    frame, _ = AnomalyDataset(seed=42).make('break')
    detection = pipe.detect(frame)
    assert detection['bbox'][2] < 200
    assert detection['anomaly_bbox'][2] > 390
    assert detection['width'] == detection['bbox'][2]
    assert {x['type'] for x in anomaly.detect(frame, detection)} == {'break'}


def test_no_pipe_frame_does_not_create_anomaly(pipeline):
    pipe, anomaly = pipeline
    frame = np.full((480, 640, 3), (55, 45, 25), np.uint8)
    assert anomaly.detect(frame, pipe.detect(frame)) == []


def test_hsv_mask_quality_on_separate_noise_seeds(pipeline):
    pipe, _ = pipeline
    params = {name: getattr(pipe, name) for name in ['h_min', 'h_max', 's_min', 's_max', 'v_min', 'v_max']}
    for seed in (13, 87):
        assert HSVEvaluator(num_frames=8, seed=seed).evaluate(params) > 0.90


@pytest.mark.parametrize('parameters', [
    {'h_min': -1}, {'h_max': 180}, {'h_min': 30, 'h_max': 10},
    {'s_max': 256}, {'v_min': float('nan')}, {'h_min': 4.5},
    {'min_area': 0}, {'min_area': float('inf')}, {'blur_kernel': 10000},
])
def test_invalid_detector_parameters_fail_before_frames(parameters):
    with pytest.raises(ValueError):
        PipeDetector(**parameters)
