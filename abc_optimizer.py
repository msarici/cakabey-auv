"""
abc_optimizer.py — Artificial Bee Colony Optimizer
Çakabey AUV | TEKNOCAK 2026

Çok ileri seviye değil ama temel optimizasyon denemeleri için yeterli.

Reproducibility: ctor `seed` parametresi alır. None ise sistem rasgeleliği,
sabit bir int verirsen koşular birebir aynı sonucu üretir. DTR rapor
sayılarının jüri tarafından da doğrulanabilmesi için seed=42 kullanılmıştır.
"""

import random


class ABCOptimizer:
    def __init__(self, bounds, fitness_fn, colony_size=20, limit=10,
                 iterations=30, maximize=True, seed=42, seed_solutions=None):
        """
        seed_solutions: opsiyonel, başlangıç kolonisine enjekte edilecek
            "warm-start" çözümleri (örn. config.yaml'daki mevcut değerler).
            Bu sayede ABC asla referans seviyenin altına düşmez; ya yakalar
            ya iyileştirir. None ise tamamen rasgele başlar.
        """
        self.bounds = bounds
        self.fitness_fn = fitness_fn
        self.colony_size = colony_size
        self.limit = limit
        self.iterations = iterations
        self.maximize = maximize
        # Encapsulated RNG: global random'ı kirletmez, deterministic koşu
        self.rng = random.Random(seed)
        self.seed_solutions = seed_solutions or []

        self.food_sources = []
        self.trial_counts = []
        self.scores = []

    def _random_solution(self):
        return [self.rng.uniform(low, high) for low, high in self.bounds]

    def _clip(self, solution):
        out = []
        for value, (low, high) in zip(solution, self.bounds):
            out.append(max(low, min(high, value)))
        return out

    def _better(self, a, b):
        return a > b if self.maximize else a < b

    def _neighbor(self, index):
        candidate = self.food_sources[index][:]
        other = self.rng.randrange(len(self.food_sources))
        while other == index:
            other = self.rng.randrange(len(self.food_sources))

        dim = self.rng.randrange(len(candidate))
        phi = self.rng.uniform(-1.0, 1.0)
        candidate[dim] = candidate[dim] + phi * (candidate[dim] - self.food_sources[other][dim])
        return self._clip(candidate)

    def run(self):
        # Warm-start: ilk N pozisyona seed_solutions konur, kalanı rasgele.
        # Böylece ABC referans çözümü görür ve oradan iyileştirmeye çalışır.
        seeds = list(self.seed_solutions)[: self.colony_size]
        randoms = [self._random_solution()
                   for _ in range(self.colony_size - len(seeds))]
        self.food_sources = [self._clip(s) for s in seeds] + randoms
        self.trial_counts = [0] * self.colony_size
        self.scores = [self.fitness_fn(sol) for sol in self.food_sources]

        best_idx = max(range(self.colony_size), key=lambda i: self.scores[i]) if self.maximize else min(range(self.colony_size), key=lambda i: self.scores[i])
        best_solution = self.food_sources[best_idx][:]
        best_score = self.scores[best_idx]

        for _ in range(self.iterations):
            # employed bees
            for i in range(self.colony_size):
                candidate = self._neighbor(i)
                score = self.fitness_fn(candidate)
                if self._better(score, self.scores[i]):
                    self.food_sources[i] = candidate
                    self.scores[i] = score
                    self.trial_counts[i] = 0
                else:
                    self.trial_counts[i] += 1

            # onlooker bees
            worst = min(self.scores) if self.maximize else max(self.scores)
            shifted = []
            for s in self.scores:
                shifted.append((s - worst + 1e-6) if self.maximize else (worst - s + 1e-6))
            total = sum(shifted)
            probs = [x / total for x in shifted]

            for _ in range(self.colony_size):
                i = self.rng.choices(range(self.colony_size), weights=probs, k=1)[0]
                candidate = self._neighbor(i)
                score = self.fitness_fn(candidate)
                if self._better(score, self.scores[i]):
                    self.food_sources[i] = candidate
                    self.scores[i] = score
                    self.trial_counts[i] = 0
                else:
                    self.trial_counts[i] += 1

            # scout bees - elite preservation: global-best food source'u koru
            current_best_idx = max(range(self.colony_size), key=lambda i: self.scores[i]) if self.maximize else min(range(self.colony_size), key=lambda i: self.scores[i])
            for i in range(self.colony_size):
                if self.trial_counts[i] >= self.limit and i != current_best_idx:
                    self.food_sources[i] = self._random_solution()
                    self.scores[i] = self.fitness_fn(self.food_sources[i])
                    self.trial_counts[i] = 0

            best_idx = max(range(self.colony_size), key=lambda i: self.scores[i]) if self.maximize else min(range(self.colony_size), key=lambda i: self.scores[i])
            if self._better(self.scores[best_idx], best_score):
                best_score = self.scores[best_idx]
                best_solution = self.food_sources[best_idx][:]

        return best_solution, best_score