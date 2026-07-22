import os
import matplotlib.pyplot as plt


def extract_routes(edges, depot=0):
    """
    選択されたアークから、デポを起点とするルートを復元する。
    """
    successors = {}

    for i, j in edges:
        successors.setdefault(i, []).append(j)

    routes = []

    for first_customer in successors.get(depot, []):
        route = [depot, first_customer]
        current = first_customer
        visited = {first_customer}

        while current != depot:
            next_nodes = successors.get(current, [])

            if len(next_nodes) != 1:
                print(
                    f"Warning: node {current} has "
                    f"{len(next_nodes)} outgoing arcs."
                )
                break

            next_node = next_nodes[0]
            route.append(next_node)

            if next_node == depot:
                break

            if next_node in visited:
                print("Warning: subtour detected:", route)
                break

            visited.add(next_node)
            current = next_node

        routes.append(route)

    return routes


def plot_routes(nodes, routes, filename):
    os.makedirs("results", exist_ok=True)

    plt.figure(figsize=(8, 8))

    customer_xs = [
        nodes[i][0]
        for i in range(1, len(nodes))
    ]

    customer_ys = [
        nodes[i][1]
        for i in range(1, len(nodes))
    ]

    plt.scatter(
        customer_xs,
        customer_ys,
        s=250,
        facecolors="white",
        edgecolors="black",
        zorder=3
    )

    depot_x, depot_y = nodes[0]

    plt.scatter(
        [depot_x],
        [depot_y],
        s=300,
        facecolors="gold",
        edgecolors="black",
        marker="s",
        zorder=3
    )

    for i, (x_coord, y_coord) in enumerate(nodes):
        plt.text(
            x_coord,
            y_coord,
            str(i),
            fontsize=12,
            ha="center",
            va="center",
            zorder=4
        )

    colors = [
        "red",
        "blue",
        "green",
        "orange",
        "purple",
        "brown"
    ]

    for vehicle_index, route in enumerate(routes):
        color = colors[vehicle_index % len(colors)]

        for position in range(len(route) - 1):
            i = route[position]
            j = route[position + 1]

            x1, y1 = nodes[i]
            x2, y2 = nodes[j]

            plt.annotate(
                "",
                xy=(x2, y2),
                xytext=(x1, y1),
                arrowprops=dict(
                    arrowstyle="->",
                    color=color,
                    lw=2,
                    shrinkA=15,
                    shrinkB=15
                ),
                zorder=2
            )

    plt.title(filename)
    plt.grid(True)
    plt.axis("equal")
    plt.xticks([])
    plt.yticks([])

    plt.tight_layout()

    plt.savefig(
        f"results/{filename}.png",
        dpi=200,
        bbox_inches="tight"
    )

    plt.close()