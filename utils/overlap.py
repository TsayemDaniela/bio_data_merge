import re
from py2neo import Graph
import animation
from tqdm import tqdm
import pandas as pd


from bio_data_merge.model.database.database import DatabaseType

graph = Graph(
    "bolt://localhost:7687", auth=("neo4j", "database"), name="main"
)

def create_query(db: DatabaseType, field_name: str):
    return f"""USE main.{db.name}
    MATCH (n:Interactor)
    RETURN n.{field_name} as result
"""

queries = [{"name": db.name, "query": create_query(db, field_name)} for db, field_name in [(DatabaseType.IntAct, "Aliases"), (DatabaseType.BioGRID, "Official_Symbol")]]

results = {}

for q in queries:
    wait = animation.Wait(text=f"Querying {q['name']} DB")
    wait.start()
    c = graph.run(q["query"])
    if c:
        results[q["name"]] = c.to_data_frame()
    else:
        print(q["name"] + "empty")
    wait.stop()

biogrid_df: pd.DataFrame = results[DatabaseType.BioGRID.name]
intact_tmp_df: pd.DataFrame = results[DatabaseType.IntAct.name]

intact_list = []
for _, name in intact_tmp_df.iterrows():
    res = re.findall(r"(?i)([A-Za-z0-9\-\ ]+)\(display_short\)", name['result'])
    if res:
        intact_list += res

intact_df = pd.DataFrame(intact_list, columns=['result'])

intact_df.to_excel('intact_df.xlsx')
biogrid_df.to_excel('biogrid_df.xlsx')

wait = animation.Wait(text="Merging data")
wait.start()
merged_df = pd.merge(biogrid_df, intact_df, on=['result'], indicator=True)
wait.stop()

merged_df.to_excel('merged_df.xlsx')

print(len(merged_df))
