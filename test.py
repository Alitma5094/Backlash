import os
from app import gen_db, init, bk, restore

SOURCE_DATABASE_NAME = "demo.db"
BACKUP_FILE_NAME = "restore.db"
OBJECT_DIRECTORY = "./bk"

os.mkdir(OBJECT_DIRECTORY)

gen_db(SOURCE_DATABASE_NAME)
init(OBJECT_DIRECTORY)
bk(SOURCE_DATABASE_NAME, OBJECT_DIRECTORY)
restore(OBJECT_DIRECTORY, BACKUP_FILE_NAME)


# compare the two files
with (
    open(SOURCE_DATABASE_NAME, "rb") as source_file,
    open(BACKUP_FILE_NAME, "rb") as backup_file,
):
    assert (
        source_file.read() == backup_file.read()
    ), "\tThe source and the backup version are not same."
print("\tSuccess.")
os.remove(SOURCE_DATABASE_NAME)
os.remove(BACKUP_FILE_NAME)
os.system("rm -rf " + OBJECT_DIRECTORY)
print("\tSuccessfully removed all the test files.")
