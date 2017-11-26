import inspect
import json
import os

from unittest import TestCase as BaseTestCase
from urllib.parse import urlencode

import sqlalchemy as sa
import yaml

from redis import StrictRedis

from playlog import config, models


class TestCase(BaseTestCase):
    BASE_URL = 'http://127.0.0.1:8080'
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.sa_engine = sa.create_engine(config.SA_URL)
        models.metadata.create_all(cls.sa_engine)
        cls.sa_conn = cls.sa_engine.connect()
        cls.redis = StrictRedis(*config.REDIS_URL)
        cls.fixtures_manager = FixturesManager(cls, cls.sa_conn, models.metadata)

    @classmethod
    def tearDownClass(cls):
        cls.sa_conn.close()
        cls.sa_conn = None
        models.metadata.drop_all(cls.sa_engine)
        cls.sa_engine = None
        cls.redis = None

    def setUp(self):
        self.clean_databases()
        self.fixtures = self.fixtures_manager.load(self._testMethodName)

    def tearDown(self):
        self.clean_databases()
        self.fixtures = None

    def clean_databases(self):
        stmt = 'TRUNCATE TABLE {} RESTART IDENTITY'.format(','.join(models.metadata.tables))
        with self.sa_conn.begin():
            self.sa_conn.execute(stmt)
        self.redis.flushdb()

    def url(self, path, **params):
        return '{}/{}?{}'.format(self.BASE_URL, path, urlencode(params))

    def get_session_id(self):
        session_id = self.redis.get('playlog:session')
        return session_id.decode('utf-8') if session_id else None

    def get_current_track(self):
        data = self.redis.get('playlog:nowplay')
        return json.loads(data.decode('utf-8')) if data else None

    def get_artists(self):
        return self.sa_conn.execute(models.artist.select()).fetchall()

    def get_albums(self):
        return self.sa_conn.execute(models.album.select()).fetchall()

    def get_tracks(self):
        return self.sa_conn.execute(models.track.select()).fetchall()

    def get_plays(self):
        return self.sa_conn.execute(models.play.select()).fetchall()

    def count_artists(self):
        return self.sa_conn.scalar(models.artist.count())

    def count_albums(self):
        return self.sa_conn.scalar(models.album.count())

    def count_tracks(self):
        return self.sa_conn.scalar(models.track.count())

    def count_plays(self):
        return self.sa_conn.scalar(models.play.count())


class FixturesManager:
    def __init__(self, test_case, sa_conn, sa_metadata):
        self.__sa_conn = sa_conn
        self.__sa_metadata = sa_metadata
        directory = os.path.join(os.path.dirname(inspect.getfile(test_case)), 'fixtures')
        if os.path.isdir(directory):
            self.__files = {
                i.replace('.yml', ''): os.path.join(directory, i)
                for i in os.listdir(directory)
                if i.endswith('.yml')
            }
        else:
            self.__files = None

    def load(self, key):
        if not (self.__files and key in self.__files):
            return
        with open(self.__files[key]) as f:
            data = yaml.load(f)
        self.__fill_database(data)
        return data

    def __fill_database(self, data):
        with self.__sa_conn.begin():
            for item in data.values():
                table, fields = item
                table = self.__sa_metadata.tables[table]
                stmt = table.insert().values(**fields)
                self.__sa_conn.execute(stmt)