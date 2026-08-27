with open("Dumas/n20w20.001.txt", "r") as f:
    # 1行目：顧客数
    N = int(f.readline().strip())

    # 次のN行：距離行列
    c = []
    for _ in range(N):
        c.append(list(map(int, f.readline().split())))

    # 次のN行：時間窓
    E = []
    L = []
    for _ in range(N):
        e, l = map(int, f.readline().split())
        E.append(e)
        L.append(l)

#txtファイルの出力
#print(N)
#for i in range(N):
#    for j in range(N):
#        print(f"{c[i][j]} ", end="")
#    print("")
#for i in range(N):
#    print(f"{E[i]} {L[i]}")