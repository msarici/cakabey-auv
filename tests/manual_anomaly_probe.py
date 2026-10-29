"""Diagnostic, not a passing safety test or a field accuracy claim.

Run: python tests/manual_anomaly_probe.py --config config.yaml
Uses the actual configured PipeDetector -> AnomalyDetector chain. Existing unit
tests feed ground-truth bounding boxes and detector defaults instead. This probe
exposes the difference without guessing new thresholds from synthetic fixtures.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import yaml
from anomaly_detector import AnomalyDetector
from evaluator_anomaly import AnomalyDataset
from evaluator_hsv import HSVEvaluator
from pipe_detector import PipeDetector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config.yaml')
    args = parser.parse_args()
    with open(args.config, encoding='utf-8') as handle:
        cfg = yaml.safe_load(handle)
    pipe = PipeDetector(**cfg['detector'])
    detector = AnomalyDetector(**{k: v for k, v in cfg['anomaly'].items() if k != 'enabled'})
    print(json.dumps({'opencv': cv2.__version__, 'numpy': np.__version__, 'seed': 42}))
    for label in AnomalyDataset.LABELS:
        frame, bbox = AnomalyDataset(seed=42).make(label)
        detection = pipe.detect(frame)
        anomalies = detector.detect(frame, detection)
        print(json.dumps({'label': label, 'expected_bbox': bbox,
                          'detected_bbox': detection['bbox'],
                          'anomalies': [a['type'] for a in anomalies]}))
    score = HSVEvaluator(seed=42).evaluate(cfg['detector'])
    print(json.dumps({'configured_hsv_synthetic_iou': score}))


if __name__ == '__main__':
    main()
