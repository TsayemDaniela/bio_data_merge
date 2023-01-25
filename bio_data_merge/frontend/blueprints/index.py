from flask import render_template

from flask import Blueprint, render_template
from bio_data_merge.model.database.database import DatabaseType

index_bp = Blueprint("index", __name__)


@index_bp.route("/")
def index():
    db_types = [db.name for db in list(DatabaseType)]
    return render_template("index.html", database_types=db_types)
