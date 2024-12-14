import subprocess
import tempfile
from datetime import datetime
import hashlib
import sqlite3
import random

import click
import os

from rich.console import Console
from rich.table import Table

import server


@click.group()
def cli():
    pass


def lock(target):
    try:
        f = open(os.path.join(target, "LOCK"), "x")
        f.close()
    except FileExistsError:
        return 1
    return 0


def unlock(target):
    os.remove(os.path.join(target, "LOCK"))


@cli.command()
@click.argument(
    "target", type=click.Path(exists=False, dir_okay=False, resolve_path=True)
)
def gen_db(target):
    with sqlite3.connect(target) as db:
        db.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, value TEXT)")
        db.executemany(
            "INSERT INTO demo (value) VALUES (?)",
            [(str(random.randint(0, 1000)),) for _ in range(10000)],
        )


@cli.command()
@click.argument(
    "directory", type=click.Path(exists=True, file_okay=False, resolve_path=True)
)
def init(directory):
    try:
        f = open(os.path.join(directory, "HEAD"), mode="x")
        f.close()

        f = open(os.path.join(directory, "INFO"), mode="x")
        f.close()
    except FileExistsError:
        click.echo("Error: Backup already exists")
        return

    os.makedirs(
        os.path.join(directory, "trees/"),
    )
    os.makedirs(os.path.join(directory, "pages/"))
    os.makedirs(os.path.join(directory, "hooks/"))

    with open(os.path.join(directory, "hooks/" "pre-backup.sh"), "x") as f:
        f.write("#!/bin/bash\n# Run before a backup is made.")
    subprocess.run(["chmod", "u+x", os.path.join(directory, "hooks/" "pre-backup.sh")])

    with open(os.path.join(directory, "hooks/" "post-backup.sh"), "x") as f:
        f.write("#!/bin/bash\n# Run after a backup is made.")
    subprocess.run(["chmod", "u+x", os.path.join(directory, "hooks/" "post-backup.sh")])

    with open(os.path.join(directory, "hooks/" "pre-restore.sh"), "x") as f:
        f.write("#!/bin/bash\n# Run before a restore is made.")
    subprocess.run(["chmod", "u+x", os.path.join(directory, "hooks/" "pre-restore.sh")])

    with open(os.path.join(directory, "hooks/" "post-restore.sh"), "x") as f:
        f.write("#!/bin/bash\n# Run after a restore is made.")
    subprocess.run(
        ["chmod", "u+x", os.path.join(directory, "hooks/" "post-restore.sh")]
    )

    click.echo("Initialized backup")


@cli.command()
@click.argument(
    "source", type=click.Path(exists=True, dir_okay=False, resolve_path=True)
)
# TODO: Make target optional and use current directory be default
@click.argument(
    "target", type=click.Path(exists=True, file_okay=False, resolve_path=True)
)
def bk(source, target):
    if lock(target) == 1:
        click.echo("Error: backup locked, please wait for other instances to finish")
    try:
        with open(os.path.join(target, "HEAD"), "r") as f:
            current_head = f.readline()
    except FileNotFoundError:
        click.echo("Error: Target directory is not a valid backup")
        return

    result = subprocess.run([os.path.join(target, "hooks/", "pre-backup.sh")])
    if result.returncode != 0:
        click.echo(
            "Error: pre-backup hook exited with non-zero exit code "
            + str(result.returncode)
        )
        return

    db_source_connection = sqlite3.connect(source)
    db_bk_path = os.path.join(tempfile.gettempdir(), "temp.db")
    db_temp_connection = sqlite3.connect(db_bk_path)

    db_source_connection.backup(db_temp_connection)

    db_source_file = open(db_bk_path, "rb")

    # if not db_source_file.read(16) == b"SQLite format 3\x00":
    #     click.echo("Error: invalid source database")
    #     return
    #
    db_source_file.seek(16, os.SEEK_SET)
    page_size = int.from_bytes(db_source_file.read(2), "little") * 256
    # click.echo(page_size)

    db_source_file.seek(28, os.SEEK_SET)
    page_count = int.from_bytes(db_source_file.read(4), "big")
    # click.echo(page_count)

    pages = []
    for page_number in range(page_count):
        db_source_file.seek(page_number * page_size, os.SEEK_SET)

        page = db_source_file.read(page_size)
        page_hash = hashlib.sha256(page).hexdigest()

        directory, filename = page_hash[:2], page_hash[2:]
        file_path = os.path.join(target, "pages/", directory, filename)

        if not os.path.exists(file_path):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as page_file:
                page_file.write(page)

        pages.append(page_hash)

    db_source_file.close()

    current_time = datetime.now().isoformat()
    tree_hash = hashlib.sha256(current_time.encode("utf-8")).hexdigest()
    with open(
        os.path.join(target, "trees/", tree_hash),
        "x",
    ) as tree_file:
        tree_file.write("parent " + current_head + "\n")
        tree_file.write("time " + current_time + "\n")
        tree_file.write("\n".join(pages))

    with open(os.path.join(target, "HEAD"), "w") as head_file:
        head_file.write(tree_hash)

    result = subprocess.run([os.path.join(target, "hooks/", "pre-backup.sh")])
    if result.returncode != 0:
        click.echo(
            "Error: pre-backup hook exited with non-zero exit code "
            + str(result.returncode)
        )
        return

    unlock(target)


@cli.command()
@click.argument(
    "source", type=click.Path(exists=True, file_okay=False, resolve_path=True)
)
# TODO: Make target optional and use current directory be default
@click.argument(
    "target", type=click.Path(exists=False, dir_okay=False, resolve_path=True)
)
@click.option(
    "-h",
    "--hash",
    "target_hash",
    type=str,
    default=None,
    help="Hash of tree to restore.",
)
def restore(source, target, target_hash):
    if lock(source) == 1:
        click.echo("Error: backup locked, please wait for other instances to finish")
    if target_hash:
        tree_hash = target_hash
    else:
        with open(os.path.join(source, "HEAD"), "r") as f:
            tree_hash = f.readline()

    with open(os.path.join(source, "trees/", tree_hash), "r") as tree_file:
        pages = tree_file.read().split("\n")[2:]

    db_target_file = open(target, "wb")

    for page in pages:
        page_path = os.path.join(source, "pages/", page[:2], page[2:])
        with open(page_path, "rb") as page_file:
            db_target_file.write(page_file.read())

    db_target_file.close()
    unlock(source)

    click.echo("DB restored")


@cli.command()
@click.argument(
    "source", type=click.Path(exists=True, file_okay=False, resolve_path=True)
)
def history(source):
    if lock(source) == 1:
        click.echo("Error: backup locked, please wait for other instances to finish")
    with open(os.path.join(source, "HEAD"), "r") as f:
        current_tree = f.readline()

    # hash : (time, num of pages)
    trees = {}

    while True:
        with open(os.path.join(source, "trees/", current_tree), "r") as tree_file:
            lines = tree_file.read().split("\n")

        parent = lines[0].split(" ")[1]
        time = lines[1].split(" ")[1]
        page_count = len(lines[2:])
        trees[current_tree] = (time, page_count)

        if parent == "":
            break
        else:
            current_tree = parent

    # click.echo(trees)
    table = Table(title="Backup History")

    table.add_column("Date")
    table.add_column("Pages")
    table.add_column("Hash")

    for k, v in trees.items():
        table.add_row(v[0], str(v[1]), k)

    console = Console()
    console.print(table)
    unlock(source)


@cli.command()
def serve():
    server.app.run(debug=True)


if __name__ == "__main__":
    cli()
