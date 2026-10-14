# %%

import pandas as pd

df = pd.read_csv("student-math.csv", sep=";")

features = ["G1", "G2", "failures", "absences", "studytime", "G3"]

print("CORRELATION WITH G3:")
print(df[features].corr()["G3"].sort_values(ascending=False))

print("\nSUMMARY:")
print(df[features].describe())

# %%
