import math

locations = [
    (200, 200), (330, 320), ( 17, 390),
    ( 57, 352), ( 79, 233), (  9, 316),
    (397, 279), (251, 348), (258, 157),
    (  3, 215), (214, 107), (389,   9),
    (106, 371), (198, 314), (315, 155)
]


def dist(i, j):
    x1, y1 = locations[i][0], locations[i][1]
    x2, y2 = locations[j][0], locations[j][1]
    return round(math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2))