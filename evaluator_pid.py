"""
evaluator_pid.py — PID Tuning için Step Response Evaluator
Çakabey AUV | TEKNOCAK 2026

ROV yaw dinamiğini birinci derece (first-order) modelle:
    τ * dy/dt + y = K * u

Performans metriği: ITAE (Integral of Time-weighted Absolute Error)
    ITAE = ∫ t * |e(t)| dt

Anti-windup: integral terimi output saturation oluştuğunda dondurulur.
Bu olmadan ABC tuning Ki'yi yapay olarak yüksek seçer (windup overshoot
göstermediği için cezalandırılmaz). Anti-windup gerçek pid_controller.py
ile tutarlıdır.
"""

import numpy as np


class PIDEvaluator:
    def __init__(
        self,
        system_gain=1.0,
        time_constant=0.5,
        sim_duration=5.0,
        sim_dt=0.02,
        step_input=100.0,
        output_min=-400,
        output_max=400,
    ):
        self.K = system_gain
        self.tau = time_constant
        self.duration = sim_duration
        self.dt = sim_dt
        self.step = step_input
        self.output_min = output_min
        self.output_max = output_max

        self.steps = int(sim_duration / sim_dt)

    def _run_pid_loop(self, kp, ki, kd, collect_series=False):
        """
        Tek bir simülasyon koşusu. Anti-windup uygulanır.
        collect_series=True ise t/y/error/u dizilerini de döndürür.
        """
        y = 0.0
        error = self.step
        integral = 0.0
        prev_error = error

        integral_t_e = 0.0

        ts, ys, errors, us = [], [], [], []

        for i in range(self.steps):
            t = i * self.dt

            # Derivative (first-order)
            derivative = (error - prev_error) / self.dt if i > 0 else 0.0

            # Tentative integral update
            new_integral = integral + error * self.dt

            # Tentative u with new integral
            u_tentative = kp * error + ki * new_integral + kd * derivative

            # Anti-windup: eğer u saturate olacaksa integral'i dondur
            if u_tentative > self.output_max:
                u = self.output_max
                # Integral sadece error sistemi saturation'dan çıkaracaksa güncellensin
                if error < 0:
                    integral = new_integral
            elif u_tentative < self.output_min:
                u = self.output_min
                if error > 0:
                    integral = new_integral
            else:
                u = u_tentative
                integral = new_integral

            # First-order plant: y[k+1] = y[k] + dt/τ * (K*u - y[k])
            y = y + (self.dt / self.tau) * (self.K * u - y)

            prev_error = error
            error = self.step - y

            # ITAE biriktir
            integral_t_e += t * abs(error) * self.dt

            if collect_series:
                ts.append(t)
                ys.append(y)
                errors.append(error)
                us.append(u)

        if collect_series:
            return integral_t_e, ts, ys, errors, us
        return integral_t_e

    def evaluate(self, pid_params):
        """ABC bu fonksiyonu çağırıyor. Yüksek = iyi."""
        itae = self._run_pid_loop(
            pid_params["kp"],
            pid_params["ki"],
            pid_params["kd"],
            collect_series=False,
        )
        return 1.0 / (1.0 + itae)

    def simulate(self, pid_params):
        """Görselleştirme için: t/y/error/u serileri döndürür."""
        _, ts, ys, errors, us = self._run_pid_loop(
            pid_params["kp"],
            pid_params["ki"],
            pid_params["kd"],
            collect_series=True,
        )
        return ts, ys, errors, us


if __name__ == "__main__":
    evaluator = PIDEvaluator()

    default_params = {"kp": 1.0, "ki": 0.0, "kd": 0.0}
    score = evaluator.evaluate(default_params)
    print(f"Default PID (Kp=1.0, Ki=0.0, Kd=0.0): fitness = {score:.4f}")

    test_cases = [
        {"kp": 0.5, "ki": 0.0, "kd": 0.0},
        {"kp": 2.0, "ki": 0.0, "kd": 0.0},
        {"kp": 5.0, "ki": 0.0, "kd": 0.0},
        {"kp": 2.0, "ki": 0.1, "kd": 0.05},
        {"kp": 3.0, "ki": 0.0, "kd": 0.1},
        {"kp": 4.36, "ki": 5.0, "kd": 0.38},   # önceki ABC çıktısı, anti-windup'lı haliyle
    ]

    print("\nFarklı PID setlerinin karşılaştırması (anti-windup ON):")
    for params in test_cases:
        score = evaluator.evaluate(params)
        print(f"  Kp={params['kp']:.2f} Ki={params['ki']:.2f} Kd={params['kd']:.2f} → fitness = {score:.4f}")