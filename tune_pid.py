"""
tune_pid.py — ABC ile PID Parametre Optimizasyonu
Çakabey AUV | TEKNOCAK 2026

evaluator_pid'yi fitness fonksiyonu olarak kullanır.
abc_pid (ABC) ile Kp, Ki, Kd parametrelerini optimize eder.
Sonucu config.yaml formatında ekrana basar.
"""

import time

from evaluator_pid import PIDEvaluator
from abc_pid import PIDTuner


def main():
    print("=" * 50)
    print("ÇAKABEY AUV - ABC PID TUNING")
    print("=" * 50)

    print("First-order ROV yaw simülatörü:")
    print("  Sistem kazancı K = 1.0")
    print("  Zaman sabiti τ = 0.5 s")
    print("  Step input = 100 piksel")
    print("  Simülasyon = 5 saniye, dt = 0.02 s (50 Hz)")
    print("  Fitness = 1 / (1 + ITAE)")

    evaluator = PIDEvaluator()

    # Referans: config.yaml default
    default_params = {"kp": 1.0, "ki": 0.0, "kd": 0.0}
    default_score = evaluator.evaluate(default_params)
    print(f"\nReferans (config default Kp=1.0, Ki=0.0, Kd=0.0):")
    print(f"  fitness = {default_score:.6f}")

    # ABC tuning
    print("\nABC algoritması çalışıyor...")
    print("Koloni: 20 arı, iterasyon: 30")
    print("Bu işlem yaklaşık 10-30 saniye sürer.\n")

    tuner = PIDTuner(evaluator=evaluator.evaluate)

    start = time.time()
    result = tuner.optimize(iterations=30)
    elapsed = time.time() - start

    print("=" * 50)
    print("SONUÇLAR")
    print("=" * 50)
    print(f"Optimizasyon süresi: {elapsed:.1f} saniye")
    print(f"\nReferans fitness:  {default_score:.6f}")
    print(f"ABC sonucu fitness: {result['score']:.6f}")
    iyilesme_orani = (result['score'] / default_score - 1) * 100 if default_score > 0 else 0
    print(f"İyileşme oranı:    %{iyilesme_orani:.1f}")

    print("\nOptimal PID parametreleri:")
    print(f"  Kp: {result['kp']:.4f}")
    print(f"  Ki: {result['ki']:.4f}")
    print(f"  Kd: {result['kd']:.4f}")

    print("\nconfig.yaml'a yapıştırılabilecek format:")
    print("-" * 30)
    print("pid:")
    print("  yaw:")
    print(f"    kp: {result['kp']:.4f}")
    print(f"    ki: {result['ki']:.4f}")
    print(f"    kd: {result['kd']:.4f}")
    print("    output_min: -400")
    print("    output_max: 400")
    print("-" * 30)

    # Bonus: optimal parametre ile simulasyonun nasıl gittiğini göster
    print("\nOptimal PID ile step response detayları:")
    ts, ys, errors, us = evaluator.simulate({
        "kp": result["kp"],
        "ki": result["ki"],
        "kd": result["kd"],
    })

    # Step response'un kritik anları
    print(f"  Başlangıç hatası: {errors[0]:.1f}")
    print(f"  1.0 saniyede hata: {errors[int(1.0/0.02)]:.1f}")
    print(f"  2.5 saniyede hata: {errors[int(2.5/0.02)]:.1f}")
    print(f"  Son hata (5s): {errors[-1]:.2f}")

    # Overshoot var mı?
    min_error = min(errors)
    if min_error < 0:
        overshoot = abs(min_error) / errors[0] * 100
        print(f"  Overshoot: %{overshoot:.1f}")
    else:
        print(f"  Overshoot: yok (kritik veya overdamped)")


if __name__ == "__main__":
    main()