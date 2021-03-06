from copy import copy
import random
import os

import psycopg2

__all__ = ['Database']

connection = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST'),
    port=os.getenv('POSTGRES_PORT'),
    database=os.getenv('POSTGRES_DATABASE'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'))


class Model:

    @classmethod
    def _insert(cls, table, data, update_data, constraint):
        columns_count = len(data)
        columns, values = zip(*data)
        columns = map(str, columns)
        values = list(map(str, values))

        if update_data == None:
            conflict_query = 'DO NOTHING'
        else:
            update_columns, update_values = zip(*update_data)
            strs = map(lambda _: '{} = %s'.format(_), update_columns)
            values.extend(update_values)
            conflict_query = '({}) DO UPDATE SET {}'.format(','.join(constraint), ', '.join(strs))
        query = 'INSERT INTO {} ({}) VALUES ({}) ON CONFLICT {}'.format(table,
                                                                        ','.join(columns), ','.join(['%s'] * columns_count),
                                                                        conflict_query)
        connection.cursor().execute(query, values)

    @classmethod
    def insert_one(cls, table, data, update_data=None, constraint=None):
        cls._insert(table, data, update_data, constraint)
        connection.commit()

    @classmethod
    def insert_all(cls, table, data_list, update_data=None, constraint=None):
        for data in data_list:
            cls._insert(table, data, update_data, constraint)
        connection.commit()

    @classmethod
    def commit(cls, query, params):
        db = connection.cursor()
        db.execute(query, params)
        connection.commit()

    @classmethod
    def fetch_all(cls, query, params):
        db = connection.cursor()
        db.execute(query, params)
        return db.fetchall()

    @classmethod
    def fetch_one(cls, query, params):
        db = connection.cursor()
        db.execute(query, params)
        return db.fetchone()


class User(Model):

    def __init__(self, id, first_name, second_name, telegram_id):
        self._id = id
        self._first_name = first_name
        self._second_name = second_name
        self._telegram_id = telegram_id

    @property
    def id(self):
        return self._id

    @property
    def first_name(self):
        return self._first_name

    @property
    def second_name(self):
        return self._second_name

    @property
    def telegram_id(self):
        return self._telegram_id

    def is_approved(self):
        query = 'SELECT is_approved FROM approved WHERE user_id = %s'
        row = self.fetch_one(query, [self.id])
        return False if row is None else row[0]

    def is_admin(self):
        query = 'SELECT is_admin FROM users WHERE id = %s'
        row = self.fetch_one(query, [self.id])
        return row[0]

    @classmethod
    def from_id(cls, user_id):
        query = 'SELECT id, first_name, second_name, telegram_id FROM users WHERE id = %s'
        row = cls.fetch_one(query, [user_id])

        if row is None:
            return None
        return cls(*row)

    @classmethod
    def from_telegram_id(cls, telegram_id):
        query = 'SELECT id, first_name, second_name, telegram_id FROM users WHERE telegram_id = %s'
        row = cls.fetch_one(query, [telegram_id])

        if row is None:
            return None
        return cls(*row)


class Event(Model):

    def __init__(self, id, name):
        self._id = id
        self._name = name

    @classmethod
    def from_id(cls, event_id):
        query = 'SELECT id, name FROM events WHERE id = %s'
        row = cls.fetch_one(query, [event_id])

        if row is None:
            return None
        return cls(*row)

    @property
    def id(self):
        return self._id

    def was_build(self):
        query = 'SELECT from_id FROM victims WHERE event_id = %s'
        row = self.fetch_one(query, [self.id])
        return row != None

    def _check_build(self, from_ids, to_ids):
        for from_id, to_id in zip(from_ids, to_ids):
            if from_id == to_id:
                return False
        return True

    def build(self):
        query = 'SELECT user_id FROM participants WHERE event_id = %s'
        rows = self.fetch_all(query, [self.id])

        from_ids = [_[0] for _ in rows]
        while True:
            to_ids = copy(from_ids)
            random.shuffle(to_ids)
            if self._check_build(from_ids, to_ids):
                break

        data_list = [[('event_id', self.id), ('from_id', _[0]), ('to_id', _[1])] for _ in zip(from_ids, to_ids)]
        self.insert_all('victims', data_list)
        return list(zip(from_ids, to_ids))

    def add_participant(self, user):
        query = 'INSERT INTO participants (event_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING'
        self.commit(query, [self.id, user.id])

    def get_participants(self):
        query = 'SELECT user_id FROM participants WHERE event_id = %s'
        rows = self.fetch_all(query, [self.id])
        if rows == None:
            return []
        return [_[0] for _ in rows]

    def has_participant(self, user):
        query = 'SELECT event_id, user_id FROM participants WHERE event_id = %s AND user_id = %s'
        row = self.fetch_one(query, [self.id, user.id])
        return row != None

    def find_victim(self, user):
        query = 'SELECT to_id FROM victims WHERE event_id = %s AND from_id = %s'
        row = self.fetch_one(query, [self.id, user.id])
        if row is None:
            return None
        return User.from_id(row[0])

    def find_santa(self, user):
        query = 'SELECT from_id FROM victims WHERE event_id = %s AND to_id = %s'
        row = self.fetch_one(query, [self.id, user.id])
        if row is None:
            return None
        return User.from_id(row[0])

    def find_interests(self, user):
        query = 'SELECT interests FROM interests WHERE event_id = %s AND user_id = %s'
        row = self.fetch_one(query, [self.id, user.id])
        if row is None:
            return None
        return row[0]

    def save_interests(self, user, interests):
        query = 'INSERT INTO interests (event_id, user_id, interests) VALUES (%s, %s) ON CONFLICT DO UPDATE'
        data = [('event_id', self.id), ('user_id', user.id), ('interests', interests)]
        self.insert_one('interests', data, [('interests', interests)], ('event_id', 'user_id'))


class Database:

    def create_user(self, telegram_user):
        data = [('telegram_id', telegram_user.id),
                ('first_name', telegram_user.first_name),
                ('second_name', telegram_user.last_name)]

        Model.insert_one('users', data)
        return self.find_user(telegram_id=telegram_user.id)

    def create_event(self, name):
        data = [('name', name)]

        Model.insert_one('events', data)

    def find_user(self, user_id=None, telegram_id=None):
        if user_id is not None:
            return User.from_id(user_id)
        elif telegram_id is not None:
            return User.from_telegram_id(telegram_id)
        return None

    def find_event(self, event_id):
        return Event.from_id(event_id)

    def approve_user(self, user):
        Model.insert_one('approved', [('user_id', user.id)])
