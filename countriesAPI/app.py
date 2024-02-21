import asyncio
import os
import time
import uuid
from collections import defaultdict
from functools import reduce
from typing import Annotated

import numpy
import requests
from hypercorn.asyncio import serve
from hypercorn.config import Config

from fastapi import FastAPI, Response, status, BackgroundTasks, Query
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

from countriesAPI.model import (
    CountryDataModel, ComparisonModel, TaskCreationModel, TaskStatusModel
)

app = FastAPI()
# Connect to local MongoDB instance
client = MongoClient(os.environ.get('DB_PREFIX', 'localhost'), 27017)
country_db: Database = client.country


@app.get("/")
async def index():
    """Hi"""
    return {"Hello": "Welcome to the API server"}


@app.get("/countries/{country_name}", status_code=status.HTTP_200_OK)
async def get_country_data(
    country_name: str, response: Response,
    filter_names: Annotated[str | None, Query(pattern=r"((\w+\.?)+\w+\,?)+\w")] = None
) -> CountryDataModel:
    """Get data for a country, either from the upstream API or from our local DB

    Parameters
    ----------
    country_name: str
        The 'common' name of the country as found in the upstream API.
    response: Response
        The response to this request
    filter_names: str
        A string query parameter listing the sub-fields to return. Needs to be
        a single string, so separate fields are comma separated and nested fields are
        referred to as <parent>.<child> e.g. name.official to return the country's
        official name
    """
    country_name = ' '.join([word.capitalize() for word in country_name.split(' ')])
    # Look up country name in our countries Collection
    countries: Collection = country_db.countries
    country_json = countries.find_one({"name.common": country_name})
    # Go and get it from the Rest Countries API
    if country_json is None:
        api_response = requests.get(
            f'https://restcountries.com/v3.1/name/{country_name}'
        )
        # Couldn't find this name
        if api_response.status_code == 404:
            response.status_code = status.HTTP_404_NOT_FOUND
            return CountryDataModel(name=country_name, data=None, message=f"No data found for {country_name}")

        # The Restcountries API just searches on a country name, so you may
        # get multiple results including /name/Ireland -> data for the UK!
        country_json = search_json_response_for_country(api_response.json(), country_name)

        if country_json is None:
            # Couldn't find this name, but it was found within one of the name strings returned
            response.status_code = status.HTTP_404_NOT_FOUND
            return CountryDataModel(
                name=country_name, data=None,
                message=f"No data found for {country_name}. Did you mean "
                        f"{','.join(js['name']['common'] for js in api_response.json()[:-2])} "
                        f"or {api_response.json()[-1]['name']['common']}?"
            )
        else:
            # Add to our db
            countries.insert_one(country_json)
    country_json.pop("_id")
    if filter_names is not None:
        filter_names = filter_names.split(',')
        country_json = result_filtering(country_json, filter_names=filter_names)
    return CountryDataModel(name=country_name, data=country_json)


@app.post('/countries/compare/{country_name_a}/{country_name_b}', status_code=status.HTTP_202_ACCEPTED
          )
async def compare_countries(
    country_name_a: str, country_name_b: str, background_tasks: BackgroundTasks, response: Response,
    filter_names: ComparisonModel
) -> TaskCreationModel:
    """Compares two countries for the fields given.

    This actually launches a job as a background task rather than completing and returning a result directly.
    Parameters
    ----------
    country_name_a: str
        First country in the comparison.
    country_name_b: str
        Second country in the comparison.
    background_tasks:
        Queue like object to add background tasks to.
    response:
        Response objects
    filter_names: ComparisonModel
        Model defining what comparisons to make
    """
    # Put filter_names back into the query form..
    filter_names = ','.join(filter_names.comparators)
    country_a_data, country_b_data = await asyncio.gather(
        get_country_data(country_name_a, response=Response(), filter_names=filter_names),
        get_country_data(country_name_b, response=Response(), filter_names=filter_names)
    )
    if "No data found" in country_a_data.data or "No data found" in country_b_data.data:
        response.status_code = status.HTTP_404_NOT_FOUND
        return TaskCreationModel(task_id=None, message=country_a_data.data)
    task_id = str(uuid.uuid4())
    background_tasks.add_task(
        actually_compare_countries, country_a_data, country_b_data, task_id=task_id
    )
    return TaskCreationModel(task_id=task_id, message="Task Accepted")


async def actually_compare_countries(
    country_a_data: CountryDataModel, country_b_data: CountryDataModel, task_id: str
):
    """Task to compare country data and post task status to the tasks DB table."""
    # Create task in DB
    tasks: Collection = country_db.tasks
    tasks.insert_one({"Task ID": task_id, "Status": "Running", "Result": None})
    result = {}
    data_a = country_a_data.data
    data_b = country_b_data.data

    def cmp_item(item_a, item_b):
        """Compare items and return the country with the largest result"""
        if item_a > item_b:
            return country_a_data.name
        elif item_b > item_a:
            return country_b_data.name
        else:
            return 'Equal'

    def cmp_dicts(dict_a, dict_b, res=None):
        """Compare our two dictionaries when values are numerical."""
        if res is None:
            res = {}
        for key in dict_a:
            if isinstance(dict_a[key], (int, float)):
                res[key] = cmp_item(dict_a[key], dict_b[key])
            if isinstance(dict_a[key], list) and all([isinstance(val, (int, float)) for val in dict_a[key]]):
                res[key] = [cmp_item(item_a, item_b) for item_a, item_b in zip(dict_a[key], dict_b[key])]
            if isinstance(dict_a[key], dict):
                res[key] = {}
                cmp_dicts(dict_a[key], dict_b[key], res[key])
        return res
    try:
        result = cmp_dicts(data_a, data_b)
        tasks.update_one({"Task ID": task_id}, {'$set': {'Status': "Completed", "Result": result}})
    except Exception as e:
        tasks.update_one({"Task ID": task_id}, {'$set': {'Status': "Failed"}})

    return result

@app.get('/countries/compare/result/{task_id}')
async def get_comparison_results(task_id: str, response: Response) -> TaskStatusModel:
    """Get the status of a task and the result if available

    Parameters
    ----------
    task_id: str
        Unique ID of the task.
    response: Response
        Response object
    """
    tasks: Collection = country_db.tasks
    task = tasks.find_one({"Task ID": task_id})
    if task is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return TaskStatusModel(task_id=task_id, status='Not Found', result=None)
    task.pop('_id')
    return TaskStatusModel(task_id=task["Task ID"], status=task['Status'], result=task['Result'])


def search_json_response_for_country(api_response: list[dict], country_name: str):
    """Helper method since restcountries API calls will return multiple results on a partial
    match of a country name"""
    for country_json in api_response:
        if country_json['name']['common'] == country_name:
            return country_json


def result_filtering(data: dict, filter_names: list[str]):
    """Remove all keys from the result dict which aren't in filter_names.

    I'm sure there's a better way to create a 'subset' dictionary than this..
    """
    names = [name.split('.') for name in filter_names]

    # Nested defaultdict :<
    result_gen = lambda: defaultdict(result_gen)
    results = result_gen()
    for name_group in names:
        # Copy over the data from the main dict
        result = reduce(lambda x, y: x.get(y, {}), name_group, data)
        if not result:
            continue
        # Get & possibly create the first level dict
        if len(name_group) == 1:
            temp = results
        else:
            temp = results[name_group[0]]
        # Walk through & possibly create dicts to the level with the actual data
        for subkey in name_group[1: -1]:
            temp = temp[subkey]

        temp[name_group[-1]] = result

    return results


if __name__ == "__main__":
    asyncio.run(serve(app, Config()))
