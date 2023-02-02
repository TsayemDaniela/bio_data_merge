from json import dumps
import re
import sys
from typing import Dict, List
from flask import render_template, redirect, request

from flask import Blueprint, render_template, Response
from bio_data_merge.model.database.database import DatabaseType
from py2neo import Graph, Node


def run_cypher_query(dbs: List[str], interactor_name: str) -> List[dict]:
    """Run a query using the neo4j backend"""
    biogrid_fields = [
        # "Systematic_Name",
        "Official_Symbol",
        # "Synonyms",
        # "Entrez_Gene",
    ]
    intact_fields = ["Alt_IDs", "IDs", "Aliases"]

    def _create_params(db: str) -> str:
        """Create the params string for the query"""
        match db:
            case DatabaseType.BioGRID.name:
                return " OR ".join(
                    [
                        f"interactor.{f} =~ '{interactor_name}'"
                        for f in biogrid_fields
                    ] + [
                        f"other.{f} =~ '{interactor_name}'"
                        for f in biogrid_fields
                    ]
                )
            case DatabaseType.IntAct.name:
                return " OR ".join(
                    [
                        f"interactor.{f} =~ '(?i).+(' + '{interactor_name}' +')\(display_short\)'"
                        for f in intact_fields
                    ] +  [
                        f"other.{f} =~  '(?i).+(' + '{interactor_name}' +')\(display_short\)'"
                        for f in intact_fields
                    ]
                )

    def _create_query() -> str:
        """Create the query string for the query"""
        qs = []
        for db in dbs:
            params = _create_params(db)
            query = f"""USE main.{db}
MATCH (interactor:Interactor)-[:INTERACTS_WITH]->(other:Interactor)
WHERE {params}
RETURN (interactor) as interactor_a, collect(other) as interactor_b
"""
            qs.append(query)

        # join them with UNION separating them
        final_query = "UNION\n".join(qs)
        return final_query

    graph = Graph("bolt://localhost:7687", auth=("neo4j", "database"), name="main")

    query = _create_query()
    c = graph.run(query)  # Cypher statements
    result = c.data()

    return result


interactor_search_bp = Blueprint("interactor-search", __name__)


@interactor_search_bp.route("/interactor/search", methods=["GET", "POST"])
def page():
    if request.method == "POST":
        global queryResult, interactor_name
        dbsToCheck = request.form.getlist("dbsToCheck[]")
        interactor_name = request.form.get("interactorName")
        if dbsToCheck is not None and interactor_name is not None:
            # run cypher query and set data in session dict
            queryResult = run_cypher_query(dbsToCheck, interactor_name)
        return redirect("/interactor/search/results")
    else:
        return


interactor_search_results_bp = Blueprint("interactor-search-results", __name__)


@interactor_search_results_bp.route("/interactor/search/results")
def page():
    
    return render_template(
        "interactor/search/results.html",
        queryResult=queryResult,
        resultLength=len(queryResult),
        query_name=interactor_name
    )


interactor_search_results_graph_bp = Blueprint(
    "interactor-search-results-graph", __name__
)


@interactor_search_results_graph_bp.route("/interactor/search/results/graph")
def page():
    nodes = []
    rels = []
    i = 0
    record: Dict[str, Node] 
    attr_to_check: str
    db: DatabaseType
    for record in queryResult:
        node = record["interactor_a"]
        if node.get("Aliases"):
            attr_to_check = "Aliases"
            db = DatabaseType.IntAct
        elif node.get("Official_Symbol"):
            attr_to_check = "Official_Symbol"
            db = DatabaseType.BioGRID
        _title = str(node.get(attr_to_check))
        node_dict =  {
            "title": _title, 
            "label": "interactor_a",
            "db": db.name,
            **node
        }
        if db == DatabaseType.IntAct:
            species_names = re.findall(r'^.+\|taxid:[0-9]+\(([A-Za-z0-9\-\s\)\("]+)\)$', node.get("Taxid"))
            res = re.findall(r'(?i)([A-Za-z0-9\-\_\s\)\(" ]+)\(display_short\)', _title)
            if not res:
                res = re.findall(r'(?i)([A-Za-z0-9\-\_\s\)\(" ]+)\(display_long\)', _title)
            node_dict["title"] = " | ".join(res)
            if species_names:
                species = species_names[-1] # IntAct ususally uses the last one with the biological name
                species = species.strip('\"')
                node_dict["species"] = species

        nodes.append(node_dict)
        target = i
        i += 1
        name: Node
        for name in record["interactor_b"]:
            _title = str(name.get(attr_to_check))
            actor = {
                "title": _title, 
                "label": "interactor_b",
                "db": db.name,
                **name
            }
            if db == DatabaseType.IntAct:
                species_names = re.findall(r'^.+\|taxid:[0-9]+\(([A-Za-z0-9\-\s\)\("]+)\)$', name.get("Taxid"))
                res = re.findall(r'(?i)([A-Za-z0-9\-\_\s\)\(" ]+)\(display_short\)', _title)
                if not res:
                    res = re.findall(r'(?i)([A-Za-z0-9\-\_\s\)\(" ]+)\(display_long\)', _title)
                actor["title"] = " | ".join(res)
                if species_names:
                    species = species_names[-1] # IntAct ususally uses the last one with the biological name
                    species = species.strip('\"')
                    actor["species"] = species

            try:
                source = nodes.index(actor)
            except ValueError:
                nodes.append(actor)
                source = i
                i += 1
            rels.append({"source": source, "target": target})

    res = dumps({"nodes": nodes, "links": rels})

    return Response(res, mimetype="application/json")
