from json import dumps
import sys
from typing import Dict, List
from flask import render_template, redirect, request

from flask import Blueprint, render_template, Response
from bio_data_merge.model.database.database import DatabaseType
from py2neo import Graph, Node


def run_cypher_query(dbs: List[str], interactor_name: str) -> List[dict]:
    """Run a query using the neo4j backend"""
    biogrid_fields = [
        "Systematic_Name",
        "Official_Symbol",
        "Synonyms",
        "Entrez_Gene",
    ]
    intact_fields = ["Alt_IDs", "IDs", "Aliases"]

    def _create_params(db: str) -> str:
        """Create the params string for the query"""
        match db:
            case DatabaseType.BioGRID.name:
                return " OR ".join(
                    [
                        f"interactor.{f} CONTAINS '{interactor_name}'"
                        for f in biogrid_fields
                    ]
                )
            case DatabaseType.IntAct.name:
                return " OR ".join(
                    [
                        f"interactor.{f} CONTAINS '{interactor_name}'"
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
    for record in queryResult:
        nodes.append({"title": dumps(record["interactor_a"]), "label": "interactor_a"})
        target = i
        i += 1
        for name in record["interactor_b"]:
            actor = {"title": dumps(name), "label": "interactor_b"}
            try:
                source = nodes.index(actor)
            except ValueError:
                nodes.append(actor)
                source = i
                i += 1
            rels.append({"source": source, "target": target})

    res = dumps({"nodes": nodes, "links": rels})

    return Response(res, mimetype="application/json")
