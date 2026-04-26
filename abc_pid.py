"""
abc_pid.py — PID Parametreleri için ABC Optimizasyonu
Çakabey AUV | TEKNOCAK 2026
"""

from abc_optimizer import ABCOptimizer


class PIDTuner:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def optimize(self, iterations=30):
        bounds = [
            (0.0, 5.0),   # kp
            (0.0, 1.0),   # ki
            (0.0, 1.0),   # kd
        ]

        def fitness(solution):
            kp, ki, kd = solution
            return self.evaluator({
                "kp": kp,
                "ki": ki,
                "kd": kd,
            })

        abc = ABCOptimizer(bounds=bounds, fitness_fn=fitness, iterations=iterations, maximize=True)
        best, score = abc.run()

        return {
            "kp": best[0],
            "ki": best[1],
            "kd": best[2],
            "score": score,
        }