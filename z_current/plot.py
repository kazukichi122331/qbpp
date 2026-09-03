from dist_matrix import c
from tsptw_plot import plot_tour, recover_coordinates

nodes = recover_coordinates(c)
tour        = [0, 9, 11, 2, 16, 15, 4, 1, 5, 8, 6, 10, 14, 18, 13, 17, 7, 3, 12, 20, 19, 0]

plot_tour(
    nodes,
    tour,
    ready_times,
    wait_times,
    arrival_times,
    due_times,
    travel_time,
    filename
)