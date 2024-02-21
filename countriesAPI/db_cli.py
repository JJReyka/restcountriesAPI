import os

import click
import requests
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from countriesAPI.app import search_json_response_for_country


@click.group()
def cli():
    pass


@cli.command(name='create_db')
@click.argument('country_names', nargs=-1)
def create_db_with_entries(country_names):
    """Adds space separated COUNTRY NAMES data to the database."""
    client = MongoClient(os.environ.get('DB_PREFIX', 'localhost'), 27017)
    country_db: Database = client.country
    countries: Collection = country_db.countries
    for country in country_names:
        api_response = requests.get(
            f'https://restcountries.com/v3.1/name/{country}'
        )
        # Couldn't find this name
        if api_response.status_code == 404:
            continue
        country_json = search_json_response_for_country(api_response.json(), country)
        if country_json is not None:
            countries.insert_one(country_json)
