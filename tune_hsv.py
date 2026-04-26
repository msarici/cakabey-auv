"""
tune_hsv.py — ABC ile HSV Parametre Optimizasyonu
Çakabey AUV | TEKNOCAK 2026

evaluator_hsv'yi fitness fonksiyonu olarak kullanır.
abc_optimizer üzerinden ABC algoritmasını çalıştırır.
Sonucu config.yaml formatında ekrana basar.
"""

import time

from evaluator_hsv import HSVEvaluator
from abc_hsv import HSVTuner


def main():
    print("=" * 50)
    print("ÇAKABEY AUV - ABC HSV TUNING")
    print("=" * 50)

    # Evaluator'ı bir kere oluştur, dataset'i hazırla
    print("Sentetik dataset hazırlanıyor (20 frame)...")
    evaluator = HSVEvaluator(num_frames=20)

    # Default parametreleri ölç (referans)
    default_params = {
        "h_min": 10, "h_max": 25,
        "s_min": 100, "s_max": 255,
        "v_min": 80, "v_max": 255,
    }
    default_score = evaluator.evaluate(default_params)
    print(f"\nReferans (config.yaml default) IoU: {default_score:.4f}")

    # ABC tuner'a evaluator.evaluate fonksiyonunu fitness olarak ver
    print("\nABC algoritması çalışıyor...")
    print("Koloni: 20 arı, iterasyon: 30")
    print("Bu işlem yaklaşık 1-2 dakika sürer.\n")

    tuner = HSVTuner(evaluator=evaluator.evaluate)

    start = time.time()
    result = tuner.optimize(iterations=30)
    elapsed = time.time() - start

    print("=" * 50)
    print("SONUÇLAR")
    print("=" * 50)
    print(f"Optimizasyon süresi: {elapsed:.1f} saniye")
    print(f"\nReferans IoU:  {default_score:.4f}")
    print(f"ABC sonucu IoU: {result['score']:.4f}")
    iyilesme = result['score'] - default_score
    print(f"İyileşme:      {iyilesme:+.4f}")

    print("\nOptimal HSV parametreleri:")
    print(f"  h_min: {result['h_min']}")
    print(f"  h_max: {result['h_max']}")
    print(f"  s_min: {result['s_min']}")
    print(f"  s_max: {result['s_max']}")
    print(f"  v_min: {result['v_min']}")
    print(f"  v_max: {result['v_max']}")

    print("\nconfig.yaml'a yapıştırılabilecek format:")
    print("-" * 30)
    print("detector:")
    print(f"  h_min: {result['h_min']}")
    print(f"  h_max: {result['h_max']}")
    print(f"  s_min: {result['s_min']}")
    print(f"  s_max: {result['s_max']}")
    print(f"  v_min: {result['v_min']}")
    print(f"  v_max: {result['v_max']}")
    print("-" * 30)


if __name__ == "__main__":
    main()