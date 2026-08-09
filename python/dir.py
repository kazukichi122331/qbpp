import pyqbpp as qbpp

# 変数作成（バイナリ変数）
x = qbpp.var("x")
y = qbpp.var("y")

# 式
f = x + y

# 制約
constraint = (f <= 5) + (f >= 2)

# 確認用の解
sol = qbpp.Sol(constraint)

# x=2,y=1 はバイナリ変数ではできないので、
# 例として x=1,y=1 にする
sol.set({x: 1, y: 1})

print("f =", sol(f))
print("constraint =", sol(constraint))
print("constraint.cons =", constraint.cons(sol))