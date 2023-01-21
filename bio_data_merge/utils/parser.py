"""Parser Module"""
import gzip
import subprocess
import pgdumplib
from pathlib import Path
from enum import IntEnum
import os
import animation
import psycopg2
from sqlalchemy import create_engine
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from tempfile import NamedTemporaryFile
import pandas as pd
from typing import Callable, List, Optional, Dict, Any
from bio_data_merge.model.interactions.interaction import Interaction
from bio_data_merge.model.interactions.interaction import InteractionProperties
from bio_data_merge.model.interactions.interactor import Interactor, InteractorVariant
from bio_data_merge.model.database.database import DatabaseType
import re
from tqdm.asyncio import tqdm
from py2neo import Graph, Node, Relationship
from dataclasses import dataclass
from dotenv import load_dotenv

# load env vars
load_dotenv()
# retrieve env vars
BIOGRID_PATH = Path(os.environ.get('BIOGRID_PATH'))
STRING_PATH = Path(os.environ.get('STRING_PATH'))
INTACT_PATH = Path(os.environ.get('INTACT_PATH'))


# helper functions
def create_interactor(
        fields: List[str], row: pd.Series,
        variant: InteractorVariant, 
        interaction_dict: Dict[str, Any], 
        graph: Graph, 
        node_map: Dict[str, Node],
        id_field_name: str
    ) -> None:
    """Create an interactor from the given data."""
    dict = {}
    for header in fields:
        # preprocess header into workable field name
        h = header.replace(" ", "_").replace("(", "").replace(")", "").replace(")", "").replace(".", "").replace("#", "")
        new_h: str = re.sub(r'_(I|i)nteractor_(A|B)$', '', h)
        
        # insert data from df into dict using our new header
        dict[new_h] = str(row[header])
    
    # create an interactor and check if it's in the node node_map; if not, insert it
    interactor = Interactor(**dict)
    if node_map.get(str(getattr(interactor, id_field_name))) is None:
        x = Node("Interactor", **interactor.dict())
        node_map[str(getattr(interactor, id_field_name))] = x
        graph.create(x)

    # we store only the name (ID) of the interactor, for referencing the node map later
    interaction_dict[f"interactor_{variant.value}"] = str(getattr(interactor, id_field_name))
    return

def insert_entries(input_df: pd.DataFrame, db_index: DatabaseType, graph: Graph, id_field_name: str, loading_text: str) -> None:
    """Iterate through rows, parse data into interactions."""
    node_map: Dict[str, Node] = {}  # map of nodes, for aid in relationship definition
    int_a_fields: List[str] = []    # fields for Interactor A
    int_b_fields: List[str] = []    # fields for Interactor B
    int_props_fields: List[str] = []    # fields for Interaction properties

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
    
    # TODO: make non-blocking
    for _, row in  tqdm(input_df.iterrows(), total=len(input_df), desc=loading_text, colour="magenta", position=db_index):
        interaction_dict = {}

        create_interactor(int_a_fields, row, InteractorVariant.A, interaction_dict, graph, node_map, id_field_name)
        create_interactor(int_b_fields, row, InteractorVariant.B, interaction_dict, graph, node_map, id_field_name)

        props_dict = {}
        for header in int_props_fields:
            props_dict[header.replace(" ", "_")] = str(row[header])
        props =  InteractionProperties(**props_dict)
        interaction_dict["interaction_properties"] = props
        
        interaction = Interaction(**interaction_dict)
        a = node_map[interaction.interactor_a]
        b = node_map[interaction.interactor_b]

        graph.create(Relationship(a, "INTERACTS_WITH", b, **interaction.interaction_properties.dict()))

@dataclass
class HandlerTask:
    """defines a task to be excuted in a threadpool"""
   
    handler: Callable
    args: List[Any]

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
        # Init logic for composite DB setup
        tmp_graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"))
        db_names =  [db.name.lower() for db in DatabaseType]
        main_db_name = "main"
        
        # create and execute Cypher statements
        statements = [
            """
            CREATE COMPOSITE DATABASE main IF NOT EXISTS
            """,
            *[
                f"""
                CREATE DATABASE {db} IF NOT EXISTS
                """ for db in db_names
            ],
            *[
                f"""
                CREATE ALIAS {main_db_name}.{db} IF NOT EXISTS
                    FOR DATABASE {db}
                """ for db in db_names
            ]
        ]
        for s in statements:
            tmp_graph.run(s)

        # initialize main graph connection to composite database for queries
        self._graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"), name=main_db_name)

        # tasks for async processing
        self._tasks: List[HandlerTask] = []
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._futures: List[Future] = []

    @staticmethod
    def _parse_biogrid_data(input_df: pd.DataFrame) -> None:
        """Parse BIOGRID data into models we can insert into graph as nodes and relationships."""
        db_index = DatabaseType.BioGRID
        biogrid_graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"), name="biogrid")  # temp handle to insert data
            
        insert_entries(input_df, db_index, biogrid_graph, "BioGRID_ID",  "BioGRID: Creating Relationships and Nodes in database")

    @staticmethod
    def _parse_string_data(input_df: pd.DataFrame) -> None:
        """Output STRING db data."""

    @staticmethod
    def _parse_intact_data(input_df: pd.DataFrame) -> None:
        """Parse IntAct db data."""
        db_index = DatabaseType.IntAct
        intact_graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"), name="intact")  # temp handle to insert data
            
        insert_entries(input_df, db_index, intact_graph, "IDs", "IntAct: Creating Relationships and Nodes in database")
        
    @staticmethod
    def read_input_data(input_data: InputData) -> Optional[pd.DataFrame]:
        """Read the file specified by the input data and return the data as a DataFrame."""
        # switch based on database type
        match input_data.database:
            case DatabaseType.BioGRID:  # expecting one file
                return [pd.concat(pd.read_csv(file, sep='\t', iterator=True, chunksize=1000)) for file in input_data.filenames][0]
            case DatabaseType.IntAct:   # expecting one file
                return [pd.concat(pd.read_csv(file, sep='\t', iterator=True, chunksize=1000)) for file in input_data.filenames][0]
            case DatabaseType.STRING:   # expecting 3 files
                for file in input_data.filenames:
                    # might need to run a subprocess to load the file into postgres, then use pandas to read the data from the database using the table name
                    # requires postgresql to be installed on the system
                    _ = subprocess.run(f"dropdb {DatabaseType.STRING.name} && createdb {DatabaseType.STRING.name}", shell=True)
                    extracted_data_cmd = subprocess.run(f"gunzip -c {file} | psql  {DatabaseType.STRING.name}", shell=True)

                    alchemyEngine   = create_engine(f"postgresql+psycopg2://postgres:@localhost/{DatabaseType.STRING.name}", pool_recycle=3600);
                    dbConnection    = alchemyEngine.connect();

                    dataFrame = pd.read_sql(
                        """
                        SELECT * FROM pg_catalog.pg_tables WHERE schemaname != 'pg_catalog' AND  schemaname != 'information_schema';
                        """,
                        dbConnection
                    )
                    pd.set_option('display.expand_frame_repr', False);

                    # Print the DataFrame
                    print(dataFrame);

                    # Close the database connection
                    dbConnection.close();

            case _:
                return None
        
    def create_handler_task(self, df: pd.DataFrame, db_type: DatabaseType)-> None:
        """Create a handler task based on the given database type."""
        handler_dict = {
            DatabaseType.BioGRID: self._parse_biogrid_data,
            DatabaseType.IntAct: self._parse_intact_data,
            DatabaseType.STRING: self._parse_string_data,
        }
        handler = handler_dict.get(db_type)
        task = HandlerTask(handler, [df])
        self._tasks.append(task)
        

    def start(self)-> None:
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

        # _add_input(input_path=BIOGRID_PATH, ext=".tab3.zip", database=DatabaseType.BioGRID)
        # _add_input(input_path=INTACT_PATH, ext=".zip", database=DatabaseType.IntAct)
        _add_input(input_path=STRING_PATH, ext=".sql.gz", database=DatabaseType.STRING)

        for entry in input_list:
            wait = animation.Wait(text=f"Reading {entry.database.name} files")
            wait.start()
            df = self.read_input_data(entry)
            wait.stop()
            self.create_handler_task(df, entry.database)

        self._futures = [self._executor.submit(task.handler, *task.args)  for task in self._tasks]
        for future in as_completed(self._futures):
            try:
                data = future.result()
            except Exception as exc:
                print('an exception occurred : %s' % (exc))
            else:
                print('result: %s' % (data))
        
           
        
    # TODO: improve shutdown method to cancel tasks
    def cleanup(self):
        """Shutdown the application."""
        print("cleanup")
        for f in self._futures:
            cancelled = f.cancel()
            if cancelled:   
                print("cancelled")
            else:
                print("not cancelled")
        
        self._executor.shutdown(cancel_futures=True)

        


parser = Parser()   # singleton instance
