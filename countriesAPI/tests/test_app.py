from unittest import mock
import pytest


class MockTasksTable:
    """A mock for the mongoDB tasks table"""

    def __init__(self):
        self.data = {}

    def insert_one(self, new_data):
        self.data[new_data['Task ID']] = new_data

    def update_one(self,task_id, new):
        self.data[task_id["Task ID"]]["Status"] = new['$set']['Status']
        self.data[task_id["Task ID"]]["Result"] = new['$set'].get('Result', None)


class MockDB:
    def __init__(self):
        self.tasks = MockTasksTable()


class MockClient:

    def __init__(self, *args, **kwargs):
        self.country = MockDB()


@pytest.mark.asyncio
async def test_actually_compare_countries():
    """Test the worker function behaves correctly - compare numerical stuff and ignore the others"""
    with mock.patch('pymongo.MongoClient', new=MockClient) as mock_client:
        from countriesAPI.app import actually_compare_countries
        res = await actually_compare_countries(
            {'Data': {'a': 10, 'b': {'c': 30, 'd': 45.5, 'e': 'abc', 'f': [10.0, 15.0]}}, 'Name': 'CountryA'},
            {'Data': {'a': 20, 'b': {'c': 30, 'd': 43.5, 'e': 'abcd', 'f': [11.0, 14.0]}}, 'Name': 'CountryB'},
            'abc'
        )

        assert res == {'a': 'CountryB', 'b': {'c': 'Equal', 'd': 'CountryA', 'f': ['CountryB', 'CountryA']}}
