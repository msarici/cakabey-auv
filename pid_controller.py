"""
pid_controller.py — Basit PID Denetleyici
Çakabey AUV | TEKNOCAK 2026
"""

import time


class PIDController:
    def __init__(
        self,
        kp=1.0,
        ki=0.0,
        kd=0.0,
        output_min=-500,
        output_max=500,
        integral_limit=None,
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.output_min = output_min
        self.output_max = output_max
        self.integral_limit = integral_limit

        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = None

    def compute(self, error):
        now = time.time()

        if self.prev_time is None:
            dt = 0.0
        else:
            dt = now - self.prev_time

        self.prev_time = now

        # P
        p = self.kp * error

        # I
        if dt > 0:
            self.integral += error * dt

        # anti-windup
        if self.ki > 0:
            if self.integral_limit is not None:
                max_integral = abs(self.integral_limit)
            else:
                max_integral = abs(self.output_max / max(self.ki, 0.001))

            if self.integral > max_integral:
                self.integral = max_integral
            elif self.integral < -max_integral:
                self.integral = -max_integral

        i = self.ki * self.integral

        # D
        if dt > 0:
            derivative = (error - self.prev_error) / dt
        else:
            derivative = 0.0

        d = self.kd * derivative

        self.prev_error = error

        output = p + i + d

        if output > self.output_max:
            output = self.output_max
        elif output < self.output_min:
            output = self.output_min

        return output

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = None