"""
fsm.py — Durum Makinesi
Çakabey AUV | TEKNOCAK 2026

SEARCH -> APPROACH -> TRACK -> LOST
MANUAL: yer istasyonundan acik komut. Otonom karari bypass eder.
"""


class FSM:
    SEARCH = "SEARCH"
    APPROACH = "APPROACH"
    TRACK = "TRACK"
    LOST = "LOST"
    MANUAL = "MANUAL"

    def __init__(
        self,
        lost_timeout=30,
        found_threshold=3,
        approach_area_min=2000,
        search_yaw_speed=150,
        forward_base_speed=200,
        track_slow_area_multiplier=1.8,
        track_slow_factor=0.6,
    ):
        self.lost_timeout = lost_timeout
        self.found_threshold = found_threshold
        self.approach_area_min = approach_area_min
        self.search_yaw_speed = search_yaw_speed
        self.forward_base_speed = forward_base_speed
        self.track_slow_area_multiplier = track_slow_area_multiplier
        self.track_slow_factor = track_slow_factor

        self.state = self.SEARCH
        self.found_count = 0
        self.lost_count = 0

    def reset(self):
        self.state = self.SEARCH
        self.found_count = 0
        self.lost_count = 0

    def set_manual(self):
        """Manuel moda gec. Otonom sayaclari sifirla — auto'ya donulurken
        sahte 'biraz once gormustum' durumlari olusmasin."""
        self.state = self.MANUAL
        self.found_count = 0
        self.lost_count = 0

    def set_auto(self):
        """Manuel'den otonoma don. SEARCH'ten temiz baslat."""
        self.state = self.SEARCH
        self.found_count = 0
        self.lost_count = 0

    def update(self, detection):
        # MANUAL'de otonom karar verme; commander ne dediyse o gider.
        # Sayaclari da islemiyoruz, manueldeyken tespit gurultusu birikmesin.
        if self.state == self.MANUAL:
            return {
                "state": self.MANUAL,
                "search_yaw": 0,
                "forward_speed": 0,
                "yaw_enabled": False,
                "forward_enabled": False,
                "message": "Manuel kumanda",
            }

        found = detection.get("found", False)
        area = detection.get("area", 0)

        if found:
            self.found_count += 1
            self.lost_count = 0
        else:
            self.lost_count += 1
            self.found_count = 0

        if self.state == self.SEARCH:
            if self.found_count >= self.found_threshold:
                self.state = self.APPROACH

        elif self.state == self.APPROACH:
            if not found and self.lost_count >= self.lost_timeout:
                self.state = self.LOST
                self.lost_count = 0
            elif found and area >= self.approach_area_min:
                self.state = self.TRACK

        elif self.state == self.TRACK:
            if not found and self.lost_count >= self.lost_timeout:
                self.state = self.LOST
                self.lost_count = 0

        elif self.state == self.LOST:
            if self.found_count >= self.found_threshold:
                self.state = self.APPROACH
            elif self.lost_count >= self.lost_timeout:
                self.state = self.SEARCH

        return self._action(area)

    def _action(self, area):
        if self.state == self.SEARCH:
            return {
                "state": self.SEARCH,
                "search_yaw": self.search_yaw_speed,
                "forward_speed": 0,
                "yaw_enabled": False,
                "forward_enabled": False,
                "message": "Hedef aranıyor",
            }

        if self.state == self.APPROACH:
            return {
                "state": self.APPROACH,
                "search_yaw": 0,
                "forward_speed": self.forward_base_speed,
                "yaw_enabled": True,
                "forward_enabled": True,
                "message": "Hedefe yaklaşılıyor",
            }

        if self.state == self.TRACK:
            speed = self.forward_base_speed
            if area > self.approach_area_min * self.track_slow_area_multiplier:
                speed = int(self.forward_base_speed * self.track_slow_factor)
            return {
                "state": self.TRACK,
                "search_yaw": 0,
                "forward_speed": speed,
                "yaw_enabled": True,
                "forward_enabled": True,
                "message": "Boru takip ediliyor",
            }

        return {
            "state": self.LOST,
            "search_yaw": self.search_yaw_speed,
            "forward_speed": 0,
            "yaw_enabled": False,
            "forward_enabled": False,
            "message": "Hedef kaybedildi",
        }