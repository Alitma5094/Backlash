import os

from flask import Flask, render_template, Response, request

app = Flask(__name__)


@app.route("/")
def index():
    with open(os.path.join("./bk", "HEAD"), "r") as f:
        current_tree = f.readline()

    if current_tree == "":
        return render_template("empty.html")
    # hash : time
    backups = {}

    while True:
        with open(os.path.join("./bk", "trees/", current_tree), "r") as tree_file:
            lines = tree_file.read().split("\n")

        parent = lines[0].split(" ")[1]
        time = lines[1].split(" ")[1]
        backups[current_tree] = time

        if parent == "":
            break
        else:
            current_tree = parent
    return render_template("index.html", backups=backups, current_hash=current_tree[:8])


@app.route("/database.sqlite/")
def database():
    data = []
    head = request.args.get("h", "")
    if head == "":
        with open("./bk/HEAD", "r") as f:
            head = f.readline()
    # Read the pages from the backup file.
    with open("./bk/trees/" + head, "r") as fp:
        pages = fp.read().split("\n")[2:]
    # Open the database.
    # with open(target, "wb") as db_file_object:
    # Iterate thourgh the pages and write them to the database.
    for page in pages:
        path = os.path.join("./bk/pages/", page[:2], page[2:])
        with open(path, "rb") as file_object:
            data.append(file_object.read())

    def generate():
        for i in range(len(data)):
            yield data[i]

    return Response(generate(), mimetype="application/octet-stream")
