import requests as r
from requests.exceptions import HTTPError
import json
import pymysql.cursors
import sqlalchemy
from sqlalchemy import MetaData, Integer, String, DateTime, Column, Table, text
import pandas as pd
import os
from settings import *

metadata = sqlalchemy.MetaData()
apiurl = "https://journal.bsuir.by/api/v1/"



def get_info(apitype):
    try:
        response = r.get(apiurl + apitype)
        response.raise_for_status()
        # print(response.text)
        return response.json()
    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}')
    except Exception as err:
        print(f'Other error occurred: {err}')


def get_fac_id(name):
    '''получить id факультета'''
    faculties = get_info("faculties")
    for fac in faculties:
        if fac['abbrev'] == name:
            return fac["id"]
    return None


def filter(groups, id):
    for group in groups:
        if group["facultyId"] == id:
            yield group


def get_groups(fac_id):
    '''получить id групп'''
    fac_groups = []
    groups = get_info("groups")
    for fic_group in filter(groups, fac_id):
        fac_groups.append(fic_group)
    return fac_groups


# 2 группы, которых не было
# for gr in groups:
#     if gr['id'] in (22233, 22648):
#         print(f"id - {gr['id']}: num - {gr['name']}")
# id - 22648: num - 860802
# id - 22233: num - 761402

def get_data(groups):
    '''save data locally'''
    try:
        os.mkdir(f'{faculty}_data')
        for group in groups:
            group_id = group["id"]
            data = get_info(f"studentGroup/schedule?id={group_id}")
            with open(f'{faculty}_data/data_{group_id}.json', 'w') as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
    except FileExistsError:
        print("Directory with data already exists")


def create_table(connection, table):
    with connection.begin():
        metadata.create_all(connection)


def insert_sql(connection, table, tosql):
    '''
    Data format: {gname, group_id, weekday, numberweek, subject, typelesson, auditory, timestart, timeend}
    '''
    with connection.begin():
        connection.execute(table.insert(), tosql)
    return None


def get_and_insert_data(groups, connection, table):
    '''save data'''
    tosql = {}
    id = 1

    # for group in groups:
    #     # group_id = group["id"]
    #     # data = get_info(f"studentGroup/schedule?id={group_id}")

    for file in os.listdir(f'{faculty}_data/'):
        with open(f'{faculty}_data/{file}') as f:
            data = json.load(f)
            tosql['group_id'] = int(data['studentGroup']['id'])

            # save group name
            try:
                tosql['gname'] = int(data['studentGroup']['name'])
            except TypeError:
                tosql['gname'] = 'NULL'

            # get data
            try:
                for day in data['schedules']:
                    tosql['weekday'] = day['weekDay']
                    for entry in day['schedule']:

                        # TODO check for k > 1
                        for k in entry['auditory']:
                            tosql['auditory'] = k
                        tosql['typelesson'] = entry['lessonType']
                        tosql['subject'] = entry['subject']
                        tosql['timestart'] = entry['startLessonTime']
                        tosql['timeend'] = entry['endLessonTime']

                        # in case > 1
                        for numberweek in entry['weekNumber']:
                            tosql['numberweek'] = numberweek
                            tosql['id'] = id
                            # insert each value
                            insert_sql(connection, table, tosql)
                            id += 1
            except TypeError:
                continue


if __name__ == "__main__":
    # get data from API
    fac_id = get_fac_id(faculty)
    groups = get_groups(fac_id)

    # save data locally to avoid api disconnection while parsing
    get_data(groups)

    engine = sqlalchemy.create_engine(
        f'mysql+pymysql://{mysqluser}:{password}@{ip}/{database}', echo=True)

    table = Table(
        tablename, metadata,
        Column('id', Integer, primary_key=True),
        Column('group_id', Integer),
        Column('gname', String(length=15)),
        Column('weekday', String(length=15)),
        Column('numberweek', Integer),
        Column('subject', String(length=30)),
        Column('typelesson', String(length=10)),
        Column('auditory', String(length=15)),
        Column('timestart', String(length=15)),
        Column('timeend', String(length=15))
    )

    with engine.connect() as conn:
        create_table(conn, table)
        # change charset for russian words
        conn.execute(text("SET collation_connection = 'utf8_general_ci'"))
        conn.execute(
            text(f"ALTER DATABASE {database} CHARACTER SET utf8 COLLATE utf8_general_ci;"))
        conn.execute(text(
            f"ALTER TABLE {tablename} CONVERT TO CHARACTER SET utf8 COLLATE utf8_general_ci;"))

        get_and_insert_data(groups, conn, table)