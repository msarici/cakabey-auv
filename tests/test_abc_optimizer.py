"""Invalid colony sizes must fail before entering neighbor selection."""
import pytest
from abc_optimizer import ABCOptimizer


@pytest.mark.parametrize('size', [0, 1, -1, True, 2.5])
def test_undersized_or_invalid_colony_fails_early(size):
    with pytest.raises(ValueError, match='colony_size'):
        ABCOptimizer([(0, 1)], lambda x: x[0], colony_size=size)


def test_two_bee_colony_completes():
    solution, score = ABCOptimizer([(0, 1)], lambda x: x[0], colony_size=2,
                                    iterations=2, seed=42).run()
    assert 0 <= solution[0] <= 1
    assert score == solution[0]


def test_empty_search_space_rejected():
    with pytest.raises(ValueError, match='bounds'):
        ABCOptimizer([], lambda x: 0)
