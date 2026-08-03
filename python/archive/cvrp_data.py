import math

locations = [
    (200, 200, 0),  (330, 320, 38), (17, 390, 25),  (57, 352, 13),
    (79, 233, 95),  (9, 316, 16),   (397, 279, 48), (251, 348, 32),
    (258, 157, 63), (3, 215, 31),   (214, 107, 48), (389, 9, 80),
    (106, 371, 61), (198, 314, 47), (315, 155, 76)]

def dist(i, j):                      # exact Euclidean distance (double)
    x1, y1 = locations[i][0], locations[i][1]
    x2, y2 = locations[j][0], locations[j][1]
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)