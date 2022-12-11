"""Parser Module"""
from pathlib import Path
from enum import IntEnum
import asyncio
import pandas as pd
from typing import List, Optional, Dict, Any
from bio_data_merge.model.interactions.interaction import Interaction
from bio_data_merge.model.interactions.interaction import InteractionProperties
from bio_data_merge.model.interactions.interactor import Interactor, InteractorVariant
from bio_data_merge.model.database.database import DatabaseType
import re
from tqdm.asyncio import tqdm
from py2neo import Graph, Node, Relationship
from dataclasses import dataclass

BIOGRID_FILES_PATH = Path.cwd().joinpath("import-dbs/BioGRID/")
STRING_FILES_PATH = Path.cwd().joinpath("import-dbs/STRING/")
INTACT_CSV_PATH = Path.cwd().joinpath("import-dbs/Intact/csv")
INTACT_TXT_PATH = Path.cwd().joinpath("import-dbs/Intact/txt")

@dataclass
class InputData:
    """Structure of the input data."""

    filenames: List[str]
    database: DatabaseType

class EntityType(IntEnum):
    """Types of entities."""

    INTERACTOR = 1
    RELATIONSHIP = 2

class Parser:
    def __init__(self):
        """Initialize the parser."""
        self._biogrid_graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"), name="biogrid")
        self._intact_graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"), name="intact")
        self._string_graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"), name="string")
        self._tasks: List[asyncio.Task] = []

    async def _parse_biogrid_data(self, input_df: pd.DataFrame) -> None:
        """Parse BIOGRID data into models we can insert into graph as nodes and relationships."""
        db_index = DatabaseType.BioGRID
        int_a_fields: List[str] = []    # fields for Interactor A
        int_b_fields: List[str] = []    # fields for Interactor B
        int_props_fields: List[str] = []    # fields for Interaction properties
        node_map: Dict[str, Node] = {}  # map of nodes, for aid in relationship definition 

        def _create_interactor(fields: List[str], row: pd.Series, variant: InteractorVariant, interaction_dict: Dict[str, Any]) -> None:
            """Create an interactor from the given data."""
            dict = {}
            for header in fields:
                # preprocess header into workable field name
                h = header.replace(" ", "_")
                new_h: str = re.sub(r'_Interactor_(A|B)$', '', h)
                
                # insert data from df into dict using our new header
                dict[new_h] = str(row[header])
            
            # create an interactor and check if it's in the node node_map; if not, insert it
            interactor = Interactor(**dict)
            if node_map.get(str(interactor.BioGRID_ID)) is None:
                x = Node("Interactor", **interactor.dict())
                node_map[str(interactor.BioGRID_ID)] = x
                self._biogrid_graph.create(x)

            # we store only the name (BioGRID ID) of the interactor, for referencing the node map later
            interaction_dict[f"interactor_{variant.value}"] = str(interactor.BioGRID_ID)
            return

        # Check for fields that end with ` A` -> interactor properties for interactor A
        # check for fields that end with ` B`  -> interactor properties for interactor B
        # the rest are interaction properties
        header: str
        for header in input_df.columns:
                if header.endswith(' A'):
                    int_a_fields.append(header)
                elif header.endswith(' B'):
                    int_b_fields.append(header)
                else:
                    int_props_fields.append(header)
        async def _insert_entries() -> None:
            """Iterate through rows, parse data into interactions."""
            desc = "Creating relationships in graph DB"
            # TODO: make non-blocking
            async for _, row in  tqdm(input_df.iterrows(), total=len(input_df), desc=desc, colour="magenta", position=db_index):
                interaction_dict = {}

                _create_interactor(int_a_fields, row, InteractorVariant.A, interaction_dict)
                _create_interactor(int_b_fields, row,  InteractorVariant.B, interaction_dict)

                props_dict = {}
                for header in int_props_fields:
                    props_dict[header.replace(" ", "_")] = str(row[header])
                props =  InteractionProperties(**props_dict)
                interaction_dict["interaction_properties"] = props
                
                interaction = Interaction(**interaction_dict)
                a = node_map[interaction.interactor_a]
                b = node_map[interaction.interactor_b]

                self._biogrid_graph.create(Relationship(a, "INTERACTS_WITH", b, **interaction.interaction_properties.dict()))
            
        self._tasks.append(asyncio.create_task(_insert_entries()))
        # await _insert_entries()

    async def _parse_string_data(self, input_df: pd.DataFrame) -> None:
        """Output STRING db data."""
        # TODO: implement parser
        # for c in input_df.columns:
            # print(c)

    async def _parse_intact_data(self, input_df: pd.DataFrame) -> None:
        """Parse IntAct db data."""
        # TODO: implement parser
        # extract the dfs
        edges_cols = []
        nodes_cols = []
        unassigned_cols = []

        nodes: Optional[pd.DataFrame] = None
        edges: Optional[pd.DataFrame] = None
        unassigned: Optional[pd.DataFrame] = None
        node_map: Dict[str, Node] = {}


        async def _create_entity(fields: List[str], row: pd.Series, entity_type: EntityType) -> None:
            """Create an interactor from the given data."""
            dict = {}
            for header in fields:
                # preprocess header into workable field name
                h = header.replace(" ", "_")
                h = h.replace("::", "_")
                
                # insert data from df into dict using our new header
                dict[h] = str(row[header])

            match entity_type:
                case EntityType.INTERACTOR:
                    # create an interactor and check if it's in the node node_map; if not, insert it
                    interactor = Interactor(**dict)
                    if node_map.get(str(interactor.IntAct_Preferred_Id)) is None:
                        x = Node("Interactor", **interactor.dict())
                        node_map[str(interactor.IntAct_Preferred_Id)] = x
                        self._intact_graph.create(x)
                case EntityType.RELATIONSHIP:
                    props = InteractionProperties(**dict)
                    # get a handle for the 2 interactors (source/target Biological role? | source/target MI Identifier)
                    # a = <TODO>
                    # b = <TODO>
                    # self._intact_graph.create(Relationship(a, "INTERACTS_WITH", b, **props.dict()))
            return

        for c in input_df.columns:
            match c:
                case "nodes":
                    nodes = input_df[c].iloc[0]
                    nodes_cols = list(nodes.columns)
                case "edges":
                    edges = input_df[c].iloc[0]
                    edges_cols = list(edges.columns)
                case "unassigned":
                    unassigned = input_df[c].iloc[0]
                    unassigned_cols = list(unassigned.columns)
                case _:
                    return
        async def _insert_entries():
            if nodes is not None:
                async for _, node in tqdm(nodes.iterrows(), position=1, desc="Creating IntAct Nodes", leave=False):
                    await _create_entity(nodes_cols, node, entity_type=EntityType.INTERACTOR)
            if edges is not None:
                async for _, edge in tqdm(edges.iterrows(), position=1, desc="Creating IntAct Relationships", leave=False):
                    await _create_entity(edges_cols, edge, entity_type=EntityType.RELATIONSHIP)
        self._tasks.append(asyncio.create_task(_insert_entries()))   
               
        
    async def read_input_data(self, input_data: InputData) -> Optional[pd.DataFrame]:
        """Read the file specified by the input data and return the data as a DataFrame."""
        # switch based on database type
        match input_data.database:
            case DatabaseType.BioGRID:
                return [pd.read_csv(file, sep='\t') for file in tqdm(input_data.filenames, position=1, desc="Reading BioGRID files", leave=False)][0]
            case DatabaseType.IntAct:
                df_dict = {}
                # TODO: can probably simply this with regex
                for file in tqdm(input_data.filenames, position=1, desc="Reading IntAct files", leave=False):
                    if file.endswith("nodes.csv"):  # nodes data
                        df_dict["nodes"] = [pd.read_csv(file)]
                    elif file.endswith("edges.csv"): # edges data
                        df_dict["edges"] = [pd.read_csv(file)]
                    elif file.endswith("unassigned.csv"): # misc data
                        df_dict["unassigned"] = [pd.read_csv(file)]
                    else:
                        print(f"File {file} not labeled with correct suffix (nodes | edges | unassigned). Not processing.")
                df = pd.DataFrame(data=df_dict)
                return df
            case DatabaseType.STRING:
                return  [pd.read_csv(file, sep=' ') for file in tqdm(input_data.filenames, position=1, desc="Reading STRING files", leave=False)][0]
            case _:
                return None
        
    async def create_handler_task(self, df: pd.DataFrame, db_type: DatabaseType)-> None:
        """Create a handler task."""
        match db_type:
            case DatabaseType.BioGRID:
                self._tasks.append(asyncio.create_task(self._parse_biogrid_data(df)))
            case DatabaseType.IntAct:
                self._tasks.append(asyncio.create_task(self._parse_intact_data(df)))
            case DatabaseType.STRING:
                self._tasks.append(asyncio.create_task(self._parse_string_data(df)))
            case _:
                return

    async def start(self)-> None:
        """Parse IntAct db data."""
        input_list: List[InputData] = []

        def _add_input(input_path: Path, ext: str, database: DatabaseType):
            """Add input data to input list."""
            input_list.append(
                InputData(
                    filenames=[str(filename) for filename in list(input_path.glob(f"*{ext}"))],
                    database=database
                )
            )

        _add_input(input_path=BIOGRID_FILES_PATH, ext=".tab3.txt", database=DatabaseType.BioGRID)
        _add_input(input_path=INTACT_CSV_PATH, ext=".csv", database=DatabaseType.IntAct)
        _add_input(input_path=STRING_FILES_PATH, ext=".v11.5.txt", database=DatabaseType.STRING)
        # TODO: add input data for STRING

        for entry in tqdm(input_list, desc="Reading input data", leave=False):
           df = await self.read_input_data(entry)
           await self.create_handler_task(df, entry.database)
           
        
    # TODO: improve shutdown method to cancel tasks
    def cleanup(self):
        """Shutdown the application."""
        for task in self._tasks:
            task.cancel()
        


parser = Parser()   # singleton instance
