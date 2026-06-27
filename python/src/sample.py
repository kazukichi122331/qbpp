import math
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2
from nodes import nodes
from plot_tour import plot_tour
# ------------------------------
# ノード座標
# ------------------------------

# ------------------------------
# 距離行列
# ------------------------------
def create_distance_matrix(nodes):
    n = len(nodes)
    dist = [[0] * n for _ in range(n)]

    for i in range(n):
        xi, yi = nodes[i]
        for j in range(n):
            xj, yj = nodes[j]
            dist[i][j] = round(math.hypot(xi - xj, yi - yj))

    return dist


distance_matrix = create_distance_matrix(nodes)

# ------------------------------
# Routing Model
# ------------------------------
manager = pywrapcp.RoutingIndexManager(
    len(distance_matrix),
    1,      # 車両数
    0       # 開始ノード
)

routing = pywrapcp.RoutingModel(manager)

# 距離関数
def distance_callback(from_index, to_index):
    from_node = manager.IndexToNode(from_index)
    to_node = manager.IndexToNode(to_index)
    return distance_matrix[from_node][to_node]

transit_callback_index = routing.RegisterTransitCallback(distance_callback)
routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

# 探索設定
search_parameters = pywrapcp.DefaultRoutingSearchParameters()

search_parameters.first_solution_strategy = (
    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
)

search_parameters.local_search_metaheuristic = (
    routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
)

search_parameters.time_limit.seconds = 10

# ------------------------------
# Solve
# ------------------------------
solution = routing.SolveWithParameters(search_parameters)

if solution:

    index = routing.Start(0)

    route = []
    distance = 0

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        route.append(node)

        previous = index
        index = solution.Value(routing.NextVar(index))
        distance += routing.GetArcCostForVehicle(previous, index, 0)

    route.append(manager.IndexToNode(index))

    print("Tour :", route)
    print("Cost :", distance)
    plot_tour(nodes, route, "")

else:
    print("No solution.")