"""
test_fsm.py — FSM durum geçişleri için unit test
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fsm import FSM


def _detection(found, area=0):
    return {"found": found, "area": area}


def test_initial_state_is_search():
    fsm = FSM()
    assert fsm.state == FSM.SEARCH


def test_search_to_approach_after_threshold():
    fsm = FSM(found_threshold=3)
    for _ in range(2):
        fsm.update(_detection(True, area=500))
        assert fsm.state == FSM.SEARCH
    fsm.update(_detection(True, area=500))
    assert fsm.state == FSM.APPROACH


def test_approach_to_track_when_close():
    fsm = FSM(found_threshold=1, approach_area_min=2000)
    fsm.update(_detection(True, area=500))   # SEARCH -> APPROACH
    assert fsm.state == FSM.APPROACH
    fsm.update(_detection(True, area=2500))  # alan yeterli -> TRACK
    assert fsm.state == FSM.TRACK


def test_approach_to_lost_after_timeout():
    fsm = FSM(found_threshold=1, lost_timeout=3)
    fsm.update(_detection(True, area=500))   # APPROACH'a geç
    for _ in range(3):
        fsm.update(_detection(False))
    assert fsm.state == FSM.LOST


def test_lost_state_persists_for_timeout_then_returns_to_search():
    """Bug fix #1 doğrulaması: LOST anında SEARCH'e geçmemeli."""
    fsm = FSM(found_threshold=1, lost_timeout=3)
    fsm.update(_detection(True, area=500))   # APPROACH
    for _ in range(3):
        fsm.update(_detection(False))
    assert fsm.state == FSM.LOST            # LOST'a geçtik
    # LOST'tan hemen sonra bir frame: hala LOST olmalı
    fsm.update(_detection(False))
    assert fsm.state == FSM.LOST
    # lost_timeout-1 frame daha boş geçer
    for _ in range(fsm.lost_timeout - 1):
        fsm.update(_detection(False))
    assert fsm.state == FSM.SEARCH


def test_lost_to_approach_when_found_again():
    fsm = FSM(found_threshold=1, lost_timeout=3)
    fsm.update(_detection(True, area=500))    # SEARCH -> APPROACH (threshold=1)
    assert fsm.state == FSM.APPROACH
    for _ in range(3):
        fsm.update(_detection(False))         # APPROACH -> LOST
    assert fsm.state == FSM.LOST
    fsm.update(_detection(True, area=500))    # LOST -> APPROACH (threshold=1)
    assert fsm.state == FSM.APPROACH
