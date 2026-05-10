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

    def optimize(self, iterations=30, colony_size=20, limit=10, seed=42,
                 default_params=None):
        """
        default_params: opsiyonel referans HSV (config.yaml'daki). Verilirse
            ABC bu noktayı initial colony'ye enjekte eder (warm-start) ve
            sonuç asla referans IoU'nun altına düşmez.
        """
        # (center, half_width) bounds - geçerli çözüm garantisi için
        # Turuncu için H ~ 5-30; geniş tutmak ABC'nin yakınsamasını
        # kötüleştiriyor. Bound'lar pratik turuncu aralığına daraltıldı.
        bounds = [
            (5, 35),     # h_center  (turuncu odaklı; sarı/kırmızı sınırı)
            (3, 25),     # h_width   (dar bir bant tipik)
            (60, 230),   # s_center
            (20, 100),   # s_width
            (60, 230),   # v_center
            (20, 100),   # v_width
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

        # default_params verilmişse (center, half_width) parametrizasyonuna
        # çevirip warm-start çözümü olarak ABC'ye besle.
        seeds = []
        if default_params is not None:
            d = default_params
            seeds.append([
                (d["h_min"] + d["h_max"]) / 2.0,
                max(1, (d["h_max"] - d["h_min"]) / 2.0),
                (d["s_min"] + d["s_max"]) / 2.0,
                max(1, (d["s_max"] - d["s_min"]) / 2.0),
                (d["v_min"] + d["v_max"]) / 2.0,
                max(1, (d["v_max"] - d["v_min"]) / 2.0),
            ])

        abc = ABCOptimizer(
            bounds=bounds,
            fitness_fn=fitness,
            colony_size=colony_size,
            limit=limit,
            iterations=iterations,
            maximize=True,
            seed=seed,
            seed_solutions=seeds,
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