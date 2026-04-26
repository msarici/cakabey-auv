"""
abc_hsv.py — HSV Parametreleri için ABC Optimizasyonu
Çakabey AUV | TEKNOCAK 2026

Bounds tasarımı: (min, max) yerine (center, half_width) parametrizasyonu kullanır.
Bu sayede ABC'nin ürettiği her çözüm her zaman geçerlidir (min < max garantisi).
Aksi halde rastgele üretilen çözümlerin yarısı geçersiz olur ve ABC converge etmez.
"""

from abc_optimizer import ABCOptimizer


class HSVTuner:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def optimize(self, iterations=30, colony_size=20, limit=10):
        # (center, half_width) bounds - geçerli çözüm garantisi için
        # H için: 0-179 aralık, center 10-170, width 5-60
        # S ve V için: 0-255 aralık, center 30-225, width 30-100
        bounds = [
            (10, 170),   # h_center
            (5, 60),     # h_width
            (30, 225),   # s_center
            (30, 100),   # s_width
            (30, 225),   # v_center
            (30, 100),   # v_width
        ]

        def fitness(solution):
            h_c, h_w, s_c, s_w, v_c, v_w = solution

            # center ± width şeklinde min/max türet
            h_min = max(0, int(h_c - h_w))
            h_max = min(179, int(h_c + h_w))
            s_min = max(0, int(s_c - s_w))
            s_max = min(255, int(s_c + s_w))
            v_min = max(0, int(v_c - v_w))
            v_max = min(255, int(v_c + v_w))

            return self.evaluator({
                "h_min": h_min,
                "h_max": h_max,
                "s_min": s_min,
                "s_max": s_max,
                "v_min": v_min,
                "v_max": v_max,
            })

        abc = ABCOptimizer(
            bounds=bounds,
            fitness_fn=fitness,
            colony_size=colony_size,
            limit=limit,
            iterations=iterations,
            maximize=True,
        )
        best, score = abc.run()

        # En iyi çözümü tekrar min/max'e çevir
        h_c, h_w, s_c, s_w, v_c, v_w = best
        return {
            "h_min": max(0, int(h_c - h_w)),
            "h_max": min(179, int(h_c + h_w)),
            "s_min": max(0, int(s_c - s_w)),
            "s_max": min(255, int(s_c + s_w)),
            "v_min": max(0, int(v_c - v_w)),
            "v_max": min(255, int(v_c + v_w)),
            "score": score,
        }