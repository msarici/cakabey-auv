"""
tune_pid.py — ABC ile PID Parametre Optimizasyonu
Çakabey AUV | TEKNOCAK 2026

evaluator_pid'yi fitness fonksiyonu olarak kullanır.
abc_pid (ABC) ile Kp, Ki, Kd parametrelerini optimize eder.
Sonucu config.yaml formatında ekrana basar.

NOT: print metinleri Windows cp1254 ile uyumlu olsun diye saf ASCII'dir
(tau, +/-, -> gibi). Docstring/comment Unicode kalabilir.
"""

import time

from evaluator_pid import PIDEvaluator
from abc_pid import PIDTuner


def main():
    print("=" * 50)
    print("CAKABEY AUV - ABC PID TUNING")
    print("=" * 50)

    print("First-order ROV yaw simulatoru:")
    print("  Sistem kazanci K = 0.25  (kalibrasyon: y_max = K*u_max = 100 = step)")
    print("  Zaman sabiti tau = 0.5 s")
    print("  Step input = 100 piksel")
    print("  Output siniri = +/-400 PWM (gercek motor ile uyumlu)")
    print("  Simulasyon = 5 saniye, dt = 0.02 s (50 Hz)")
    print("  Fitness = 1 / (1 + ITAE)")

    evaluator = PIDEvaluator()

    default_params = {"kp": 1.0, "ki": 0.0, "kd": 0.0}
    default_score, default_itae = evaluator.evaluate_with_itae(default_params)
    print("\nReferans (config default Kp=1.0, Ki=0.0, Kd=0.0):")
    print(f"  ITAE    = {default_itae:.4f}")
    print(f"  fitness = {default_score:.6f}")

    print("\nABC algoritmasi calisiyor...")
    print("Koloni: 20 ari, iterasyon: 30")
    print("Bu islem yaklasik 10-30 saniye surer.\n")

    tuner = PIDTuner(evaluator=evaluator.evaluate)

    start = time.time()
    result = tuner.optimize(iterations=30, default_params=default_params)
    elapsed = time.time() - start

    optimal_itae = (1.0 / result['score']) - 1.0 if result['score'] > 0 else float('inf')

    print("=" * 50)
    print("SONUCLAR")
    print("=" * 50)
    print(f"Optimizasyon suresi: {elapsed:.1f} saniye")
    print(f"\nReferans  ITAE: {default_itae:.4f}   (fitness {default_score:.6f})")
    print(f"ABC sonucu ITAE: {optimal_itae:.4f}   (fitness {result['score']:.6f})")
    itae_iyilesme = (default_itae - optimal_itae) / default_itae * 100 if default_itae > 0 else 0
    print(f"ITAE azalmasi:   %{itae_iyilesme:.1f}")

    print("\nOptimal PID parametreleri:")
    print(f"  Kp: {result['kp']:.4f}")
    print(f"  Ki: {result['ki']:.4f}")
    print(f"  Kd: {result['kd']:.4f}")

    print("\nconfig.yaml'a yapistirilabilecek format:")
    print("-" * 30)
    print("pid:")
    print("  yaw:")
    print(f"    kp: {result['kp']:.4f}")
    print(f"    ki: {result['ki']:.4f}")
    print(f"    kd: {result['kd']:.4f}")
    print("    output_min: -400")
    print("    output_max: 400")
    print("-" * 30)

    print("\nOptimal PID ile step response detaylari:")
    ts, ys, errors, us = evaluator.simulate({
        "kp": result["kp"],
        "ki": result["ki"],
        "kd": result["kd"],
    })

    print(f"  Baslangic hatasi: {errors[0]:.1f}")
    print(f"  1.0 saniyede hata: {errors[int(1.0/0.02)]:.1f}")
    print(f"  2.5 saniyede hata: {errors[int(2.5/0.02)]:.1f}")
    print(f"  Son hata (5s): {errors[-1]:.2f}")

    min_error = min(errors)
    if min_error < 0:
        overshoot = abs(min_error) / errors[0] * 100
        print(f"  Overshoot: %{overshoot:.1f}")
    else:
        print("  Overshoot: yok (kritik veya overdamped)")


if __name__ == "__main__":
    main()
