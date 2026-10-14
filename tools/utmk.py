# -*- coding: utf-8 -*-
"""UTM-K(EPSG:5179, GRS80 횡메르카토르) ↔ WGS84 위경도 변환 (Snyder 식, 표준 라이브러리만)."""
import math
A, F = 6378137.0, 1 / 298.257222101
E2 = 2 * F - F * F
EP2 = E2 / (1 - E2)
K0, LAT0, LON0, FE, FN = 0.9996, math.radians(38), math.radians(127.5), 1000000.0, 2000000.0


def _m(p):
    return A * ((1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256) * p - (3 * E2 / 8 + 3 * E2 ** 2 / 32 + 45 * E2 ** 3 / 1024) * math.sin(2 * p)
                + (15 * E2 ** 2 / 256 + 45 * E2 ** 3 / 1024) * math.sin(4 * p) - (35 * E2 ** 3 / 3072) * math.sin(6 * p))


def to_utmk(lat, lng):
    p, l = math.radians(lat), math.radians(lng)
    n = A / math.sqrt(1 - E2 * math.sin(p) ** 2)
    t, c, a = math.tan(p) ** 2, EP2 * math.cos(p) ** 2, (l - LON0) * math.cos(p)
    x = FE + K0 * n * (a + (1 - t + c) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a ** 5 / 120)
    y = FN + K0 * (_m(p) - _m(LAT0) + n * math.tan(p) * (a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
                                                    + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a ** 6 / 720))
    return x, y


def to_wgs84(x, y):
    mu = (_m(LAT0) + (y - FN) / K0) / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1, t1 = EP2 * math.cos(p1) ** 2, math.tan(p1) ** 2
    n1 = A / math.sqrt(1 - E2 * math.sin(p1) ** 2)
    r1 = A * (1 - E2) / (1 - E2 * math.sin(p1) ** 2) ** 1.5
    d = (x - FE) / (n1 * K0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
                                           + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lng = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120) / math.cos(p1)
    return math.degrees(lat), math.degrees(lng)


if __name__ == "__main__":
    for nm, la, lo in (("서울시청", 37.5663, 126.9779), ("부산시청", 35.1798, 129.0750), ("제주시청", 33.4996, 126.5312)):
        x, y = to_utmk(la, lo)
        b = to_wgs84(x, y)
        print(nm, round(x, 1), round(y, 1), "왕복오차(m)", round(math.hypot((b[0] - la) * 111000, (b[1] - lo) * 88000), 4))
