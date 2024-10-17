
# ----------------------------------------------- #
#   ECLIPSE AUTOMATION INC. // ANTHONY BEIJES
#   PROGRAM TO PULL BACKUP FROM FANUC ROBOT CONTROLLER TO HOST
#
#   ROBOT DATA IS STORED IN SQLITE3 DB FILE, WITH FORMAT OF ROBOT CLASS
#   IF YOU CHANGE THE STRUCTURE OF THE ROBOT CLASS, THE DB FILE MUST BE DELETED
#   SO THAT THE PROGRAM CREATES A NEW ONE WITH PROPER STRUCTURE
#
#   MISC. DATA IS STORED IN JSON FILE
#
# ----------------------------------------------- #

from ftplib import FTP
from progress.bar import Bar
import time
import os
import json
from datetime import datetime
import sqlite3
import concurrent.futures

# GLOBAL VARIABLES
db_file = "RobotData.db"
json_file = "data.json"
tableName = "robots"

# Python types to SQL types
type_mapping = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER"
}


class Robot:
    name: str
    ip: str
    family: str

    def __init__(self, name, ip, family):
        self.name = name
        self.ip = ip
        self.family = family


# clear console
def clear():
    os.system('cls')


def save_json(data):  # save JSON
    try:
        with open(json_file, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print("Error while saving to json file:", e)


def load_json():  # load JSON
    if not os.path.isfile(json_file):
        open(json_file, "a")

    try:
        with open(json_file, "r") as f:
            return json.load(f)
    except Exception as ex:
        print("Error loading from json file:", ex)
        save_json({"backup_path": ""})
        return{"backup_path": ""}

def create_table():  # save SQLite db
    columns = []

    for attr_name, attr_type in Robot.__annotations__.items():
        sql_type = type_mapping.get(attr_type, "TEXT")  # Default to TEXT if type is not mapped
        if attr_name == 'name' or attr_name == 'ip':
            column = f"{attr_name} {sql_type} UNIQUE"
        else:
            column = f"{attr_name} {sql_type}"

        columns.append(column)

    columns_sql = ", ".join(columns)
    create_table_sql = f"CREATE TABLE IF NOT EXISTS {tableName} ({columns_sql});"

    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()
    cursor.execute(create_table_sql)
    connection.commit()
    connection.close()


def save_robot(robot):
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    # Check for robot name or ip already existing
    cursor.execute(f'SELECT * FROM {tableName} WHERE name = ?', (robot.name,))
    result = cursor.fetchone()
    if result:
        print("Duplicate name detected, robot not added")
        time.sleep(3)
        return 0

    cursor.execute(f'SELECT * FROM {tableName} WHERE ip = ?', (robot.ip,))

    result = cursor.fetchone()
    if result:
        print("Duplicate ip detected, robot not added")
        time.sleep(3)
        return -1

    insert_sql = f'''
    INSERT INTO {tableName} (name, ip, family) VALUES (?, ?, ?)
    '''
    cursor.execute(insert_sql, (robot.name, robot.ip, robot.family))
    connection.commit()
    connection.close()

    print(f'Robot {robot.name} added')
    time.sleep(2)


def get_robot(name):
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    cursor.execute(f'SELECT * FROM {tableName} WHERE name = ?', (name,))
    result = cursor.fetchone()

    if result:
        robot = Robot(name=result[0], ip=result[1], family=result[2])
    else:
        print(f"No robot found with name: {name}")
        robot = None

    connection.commit()
    connection.close()

    return robot


# create robot
def create_robot():
    rb_name = input("Name: ")
    ip = input("Robot IP: ")
    group = input("Group name: ")

    robot = Robot(rb_name, ip, group)
    save_robot(robot)


def delete_robot(name):  # delete robot from db

    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    cursor.execute(f'SELECT * FROM {tableName} WHERE name = ?', (name,))
    result = cursor.fetchone()

    if result:
        cursor.execute(f'DELETE FROM {tableName} WHERE name = ?', (name,))
        print(f'Robot {name} deleted')
    else:
        print(f"No robot found with name: {name}")

    time.sleep(2)
    connection.commit()
    connection.close()


# change the local path that the robot backup is stored to
def change_path():
    data = load_json()
    backup_path = data["backup_path"]
    print("-----------------------")
    print("Current path: " + backup_path)
    backup_path = input("New path: ")
    data["backup_path"] = backup_path
    save_json(data)
    print("Backup path updated.")
    time.sleep(3)


def list_robots():  # List robots sorted by PLC
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    cursor.execute(f'SELECT * FROM {tableName} ORDER BY family')
    result = cursor.fetchall()

    if result:
        for r in result:
            i = 0
            for attr_name in Robot.__annotations__.items():
                if i != 0:
                    print(' || ', end='')
                print(f'{attr_name[0]}: {r[i]} ', end='')
                i += 1
            print('')
    else:
        print(f"No robots found in DB")

    print('')
    connection.commit()
    connection.close()


def list_robots_by_grp(fam):  # list robots for a single PLC

    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    cursor.execute(f'SELECT * FROM {tableName} WHERE family = ?', (fam,))
    result = cursor.fetchall()

    if result:
        for r in result:
            i = 0
            for attr_name in Robot.__annotations__.items():
                if i != 0:
                    print(' || ', end='')
                print(f'{attr_name[0]}: {r[i]} ', end='')
                i += 1
            print('')
    else:
        print(f"No robots found in DB")

    connection.commit()
    connection.close()


def list_groups():  # list available PLCs
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    cursor.execute(f'SELECT DISTINCT family FROM {tableName}')
    result = cursor.fetchall()

    for r in result:
        print(r[0])

    connection.commit()
    connection.close()


def backup_all(group):  # backup all robots
    clear()

    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    cursor.execute(f'SELECT name FROM {tableName} WHERE family = ?', (group,))
    result = cursor.fetchall()

    connection.commit()
    connection.close()

    robot_names = [r[0] for r in result]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(backup_individual, name): name for name in robot_names}

        for future in concurrent.futures.as_completed(futures):
            rname = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"{rname} generated an exception: {exc}")

    time.sleep(3)


def backup_individual(name):  # backup a single robot
    clear()
    data = load_json()
    now = datetime.now()
    dt_string = now.strftime("%d%m%Y_%H%M")
    backup_path = data["backup_path"]
    robot = get_robot(name)

    try:
        print(f"Connecting to {robot.name}")
        ftp = FTP(robot.ip)
        ftp.login()
        robot_folder = f"{backup_path}\\{robot.name}_{dt_string}"
        os.mkdir(robot_folder)

        files = ftp.nlst()
        print("Connected!")
        print(f"Pulling backup to {robot_folder}")
        count = 0

        for file in files:
            count += 1

        with Bar('Downloading files', max=count) as bar:
            for file in files:
                with open(robot_folder + "\\" + file, "wb") as f:
                    ftp.retrbinary(f"RETR {file}", f.write)
                bar.next()

        ftp.close()
        ftp = None

    except Exception as e:
        print(f"Error backing up {robot.name}: {e}")
        time.sleep(3)

    time.sleep(2)


def init():
    # check if a last target exists - if so make sure that the credentials exist
    data = load_json()
    default_path = os.getcwd()

    try:
        backup_path = data['backup_path']
    except Exception:
        backup_path = ""

    if backup_path == "":
        print(f"Setting default path as {default_path} This can be changed in menu option 5")
        data['backup_path'] = default_path
        time.sleep(5)

    save_json(data)
    create_table()


if __name__ == "__main__":

    option = ""
    menu = "base"
    init()

    while True:

        if menu == "base":

            if option == "":
                clear()
                print("[1] Make a backup")
                print("[2] List robots")
                print("[3] Add robot")
                print("[4] Delete robot")
                print("[5] Change backup location")
                print("[6] Quit")

                option = input("Command: ")

            if option == "1":
                clear()
                menu = "backup"
                option = ""

            if option == "2":
                clear()
                list_robots()
                input('Press enter to return to menu')
                option = ""

            if option == "3":
                clear()
                create_robot()
                option = ""

            if option == "4":
                clear()
                list_robots()
                robot_name = input("Enter the name of the robot to delete: ")
                delete_robot(robot_name)
                clear()
                option = ""

            if option == "5":
                clear()
                change_path()
                menu = "base"
                option = ""

            if option == "6":
                exit()

        if menu == "backup":

            if option == "":
                clear()
                print("Backup options:")
                print("[1] All robots")
                print("[2] Select robot")
                print("[3] Back")

                option = input("Command: ")

            if option == "1":
                clear()
                list_groups()
                plc = input("Select group: ")
                backup_all(plc)
                menu = "base"
                option = ""

            if option == "2":
                clear()
                list_groups()
                grp = input("Select group: ")
                clear()
                list_robots_by_grp(grp)
                robot_name = input("Select robot: ")
                backup_individual(robot_name)
                menu = "base"
                option = ""

            if option == "3":
                menu = "base"
                option = ""
