"""
manual_input.py — Manuel Kumanda Girisi (Klavye / Gamepad)
Cakabey AUV | TEKNOCAK 2026

Yer istasyonu (laptop) tarafinda calisir. Iki kaynak:
- Gamepad (pygame.joystick): analog kontrol, varsa oncelikli.
- Klavye (pygame.key, video viewer penceresi uzerinden): fallback.

Her read() cagrisinda normalize edilmis dict doner:
    {
        "fwd": -1.0..1.0,
        "yaw": -1.0..1.0,
        "vertical": -1.0..1.0,
        "mode_toggle": bool,    # tek-shot, basildigi an True
        "emergency_stop": bool, # tek-shot
    }

Klavye-ozellikli not: pygame klavyeyi sadece kendi penceresi aktifken
okur. Bu sebeple video_viewer.py pygame penceresi acar; cv2.imshow
yerine pygame surface'ine basar. Tek pencere, tek event loop.

Source secimi: source="auto" -> gamepad varsa onu, yoksa klavye.
"""

try:
    import pygame
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False


# Xbox controller default eslemesi (pygame standart axis/button id'leri).
# Farkli controller'larda axis/button id'leri kayabilir; calistirinca
# uyari basariz.
AXIS_LEFT_X = 0
AXIS_LEFT_Y = 1
AXIS_RIGHT_X = 3
AXIS_LT = 4
AXIS_RT = 5

BTN_A = 0
BTN_B = 1


def _deadzone(value, threshold=0.12):
    """Stick deadzone — kucuk sapmalari sifirla."""
    if abs(value) < threshold:
        return 0.0
    # Deadzone disinda lineer rescale yap (kaybedilen aralik telafi).
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - threshold) / (1.0 - threshold)


def _clamp(value, lo=-1.0, hi=1.0):
    return max(lo, min(hi, value))


class ManualInput:
    def __init__(self, source="auto", deadzone=0.12):
        """
        source: "auto" / "keyboard" / "gamepad"
        deadzone: stick deadzone (0..0.5 mantikli)
        """
        if not PYGAME_OK:
            raise RuntimeError(
                "pygame yuklu degil. 'pip install pygame' veya source=None"
            )

        self.deadzone = float(deadzone)
        self._joy = None
        self._source = "keyboard"  # default fallback

        if not pygame.get_init():
            pygame.init()
        if not pygame.joystick.get_init():
            pygame.joystick.init()

        requested = (source or "auto").lower()

        if requested in ("auto", "gamepad"):
            if pygame.joystick.get_count() > 0:
                try:
                    self._joy = pygame.joystick.Joystick(0)
                    self._joy.init()
                    self._source = "gamepad"
                    print(f"[input] Gamepad: {self._joy.get_name()}")
                except Exception as e:
                    print(f"[input] Gamepad init hatasi: {e}")
                    self._joy = None
            elif requested == "gamepad":
                print("[input] Gamepad istendi ama bulunamadi. Klavyeye dustu.")

        if self._joy is None:
            self._source = "keyboard"
            print("[input] Klavye modu (W/S=fwd, A/D=yaw, R/F=dikey, "
                  "M=mod, SPACE=acil dur)")

        # Tek-shot tuslar icin onceki durum
        self._prev_mode_toggle = False
        self._prev_emergency = False

    @property
    def source(self):
        return self._source

    def read(self):
        """
        Pygame event'lerini akit, son durumu oku.
        Ayni anda hem video viewer hem buradan pygame.event.pump()
        cagrildiginda sorun yok — idempotent.
        """
        pygame.event.pump()

        if self._source == "gamepad" and self._joy is not None:
            return self._read_gamepad()
        return self._read_keyboard()

    def _read_gamepad(self):
        try:
            n_axes = self._joy.get_numaxes()
            n_buttons = self._joy.get_numbuttons()

            # Sol stick Y: yukari negatif (pygame), bizim "ileri" pozitif.
            ly = self._joy.get_axis(AXIS_LEFT_Y) if n_axes > AXIS_LEFT_Y else 0.0
            rx = self._joy.get_axis(AXIS_RIGHT_X) if n_axes > AXIS_RIGHT_X else 0.0
            lt = self._joy.get_axis(AXIS_LT) if n_axes > AXIS_LT else -1.0
            rt = self._joy.get_axis(AXIS_RT) if n_axes > AXIS_RT else -1.0

            fwd = _deadzone(-ly, self.deadzone)
            yaw = _deadzone(rx, self.deadzone)

            # Trigger'lar pygame'de -1..+1 (released=-1). 0..1'e cevir.
            lt_norm = (lt + 1.0) / 2.0
            rt_norm = (rt + 1.0) / 2.0
            vertical = _clamp(rt_norm - lt_norm)

            btn_a = bool(self._joy.get_button(BTN_A)) if n_buttons > BTN_A else False
            btn_b = bool(self._joy.get_button(BTN_B)) if n_buttons > BTN_B else False

            mode_toggle = btn_a and not self._prev_mode_toggle
            emergency = btn_b and not self._prev_emergency
            self._prev_mode_toggle = btn_a
            self._prev_emergency = btn_b

            return {
                "fwd": _clamp(fwd),
                "yaw": _clamp(yaw),
                "vertical": _clamp(vertical),
                "mode_toggle": mode_toggle,
                "emergency_stop": emergency,
            }
        except Exception as e:
            print(f"[input] Gamepad okuma hatasi: {e}")
            return self._idle()

    def _read_keyboard(self):
        try:
            keys = pygame.key.get_pressed()

            fwd = 0.0
            if keys[pygame.K_w]:
                fwd += 1.0
            if keys[pygame.K_s]:
                fwd -= 1.0

            yaw = 0.0
            if keys[pygame.K_d]:
                yaw += 1.0
            if keys[pygame.K_a]:
                yaw -= 1.0

            vertical = 0.0
            if keys[pygame.K_r]:
                vertical += 1.0
            if keys[pygame.K_f]:
                vertical -= 1.0

            m_pressed = bool(keys[pygame.K_m])
            sp_pressed = bool(keys[pygame.K_SPACE])

            mode_toggle = m_pressed and not self._prev_mode_toggle
            emergency = sp_pressed and not self._prev_emergency
            self._prev_mode_toggle = m_pressed
            self._prev_emergency = sp_pressed

            return {
                "fwd": _clamp(fwd),
                "yaw": _clamp(yaw),
                "vertical": _clamp(vertical),
                "mode_toggle": mode_toggle,
                "emergency_stop": emergency,
            }
        except Exception as e:
            print(f"[input] Klavye okuma hatasi: {e}")
            return self._idle()

    def _idle(self):
        return {
            "fwd": 0.0,
            "yaw": 0.0,
            "vertical": 0.0,
            "mode_toggle": False,
            "emergency_stop": False,
        }

    def close(self):
        try:
            if self._joy is not None:
                self._joy.quit()
        except Exception:
            pass
        self._joy = None
