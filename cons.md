### n=15(A100)
consなし
energy = 6948
violated constraints = 6
[0, 13, 8, 9, 11, 0]

consあり
cons_energy = 936
violated constraints = 0
[0, 13, 9, 4, 1, 12, 11, 5, 6, 10, 7, 2, 14, 3, 8, 0]

### n=20(A100)
consあり
cons_energy = 2956
violated constraints = 2
都市17から出る枝がありません
[0, 8, 13, 9, 4, 15, 12, 1, 6, 10, 18, 7, 2, 17]


cons無しの場合、n=15でも制約違反になる
cons有りの場合、n=15程度なら最適解を出せる場合がある。n=20以上だと厳しそう