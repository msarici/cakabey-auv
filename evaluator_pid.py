"""
evaluator_pid.py — PID Tuning için Step Response Evaluator
Çakabey AUV | TEKNOCAK 2026

ROV yaw dinamiğini birinci derece (first-order) modelle:
    tau * dy/dt + y = K * u

Performans metriği: ITAE (Integral of Time-weighted Absolute Error)
    ITAE = integral( t * |e(t)| ) dt

Anti-windup yaklaşımı (pid_controller.py ile birebir aynı):
    1. integral'i her zaman error*dt ile güncelle
    2. Ki > 0 ise integral'i max_integral ile clamp et
       (max_integral = integral_limit varsa onu, yoksa output_max / Ki)
    3. output = kp*error + ki*integral + kd*derivative
    4. output'u output_min/output_max ile clamp et
Bu yaklaşım "back-calculation" değil; integral state-clamping. Gerçek
PIDController ile aynı davranır, ABC tuning doğrudan controller'a transfer olur.

Birim tutarlılığı:
    step = 100 piksel (yaw hatası)
    u    = +/-400 PWM offset (gerçek motor sınırı, vehicle.py PWM clip ile uyumlu)
    K    = 0.25  ->  steady-state y_max = K * u_max = 0.25 * 400 = 100 piksel = step
Bu kalibrasyon çıkışı step ile aynı seviyede tutar; doyma fizik dışı
overshoot üretmez. K, gerçek araç tepkisine kalibre edildiğinde ABC tuning
doğrudan gerçek davranışa transfer olur.
"""

import numpy as np


class PIDEvaluator:
    def __init__(
        self,
        system_gain=0.25,
        time_constant=0.5,
        sim_duration=5.0,
        sim_dt=0.02,
        step_input=100.0,
        output_min=-400,
        output_max=400,
        integral_limit=None,
    ):
        self.K = system_gain
        self.tau = time_constant
        self.duration = sim_duration
        self.dt = sim_dt
        self.step = step_input
        self.output_min = output_min
        self.output_max = output_max
        self.integral_limit = integral_limit

        self.steps = int(sim_duration / sim_dt)

    def _clamp_integral(self, integral, ki):
        """PIDController._clamp_integral mantığının birebir kopyası."""
        if ki <= 0:
            return integral
        if self.integral_limit is not None:
            max_integral = abs(self.integral_limit)
        else:
            max_integral = abs(self.output_max / ki)
        if integral > max_integral:
            return max_integral
        if integral < -max_integral:
            return -max_integral
        return integral

    def _run_pid_loop(self, kp, ki, kd, collect_series=False):
        """
        Tek bir simülasyon koşusu. PIDController.compute() ile aynı sıra:
        integral update -> integral clamp -> output -> output clamp.
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

            # 1) Integral update (her zaman, dt > 0)
            integral += error * self.dt

            # 2) Anti-windup: integral state clamp (Ki > 0 ise)
            integral = self._clamp_integral(integral, ki)

            # 3) Derivative (i=0'da derivative kick'i engelle)
            derivative = (error - prev_error) / self.dt if i > 0 else 0.0

            # 4) Output ve output clamp
            u = kp * error + ki * integral + kd * derivative
            if u > self.output_max:
                u = self.output_max
            elif u < self.output_min:
                u = self.output_min

            # 5) First-order plant: y[k+1] = y[k] + dt/tau * (K*u - y[k])
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

    def evaluate_with_itae(self, pid_params):
        """Hem skoru hem ham ITAE'yi döndürür (raporlama için)."""
        itae = self._run_pid_loop(
            pid_params["kp"],
            pid_params["ki"],
            pid_params["kd"],
            collect_series=False,
        )
        return 1.0 / (1.0 + itae), itae

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
    ]

    print("\nFarkli PID setlerinin karsilastirmasi (anti-windup ON):")
    for params in test_cases:
        score = evaluator.evaluate(params)
        print(f"  Kp={params['kp']:.2f} Ki={params['ki']:.2f} Kd={params['kd']:.2f} -> fitness = {score:.4f}")