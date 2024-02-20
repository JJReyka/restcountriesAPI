import asyncio
import uuid
from collections import defaultdict
from functools import reduce
from typing import Annotated

import requests
from hypercorn.asyncio import serve
from hypercorn.config import Config

from fastapi import FastAPI, Response, status, BackgroundTasks, Query
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

app = FastAPI()
# Connect to local MongoDB instance
client = MongoClient("localhost", 27017)
country_db: Database = client.country


@app.get("/")
async def index():
    """Hi"""
    return {"Hello": "Welcome to the API server"}


@app.get("/countries/{country_name}", status_code=status.HTTP_200_OK)
async def get_country_data(
    country_name: str, response: Response,
    filter_names: Annotated[str | None, Query(pattern=r"((\w+\.?)+\w+\,?)+\w")] = None
):
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
            return {"Name": country_name, "Data": f"No data found for {country_name}"}

        # The Restcountries API just searches on a country name, so you may
        # get multiple results including /name/Ireland -> data for the UK!
        country_json = search_json_response_for_country(api_response, countries, country_name)
        if country_json is None:
            # Couldn't find this name, but it was found within one of the name strings returned
            response.status_code = status.HTTP_404_NOT_FOUND
            return {
                "Name": country_name,
                "Data": f"No data found for {country_name}. Did you mean "
                        f"{','.join(js['name']['common'] for js in api_response.json()[:-2])} "
                        f"or {api_response.json()[-1]['name']['common']}?"
            }

    country_json.pop("_id")
    if filter_names is not None:
        filter_names = filter_names.split(',')
        country_json = result_filtering(country_json, filter_names=filter_names)
    return {"Name": country_name, "Data": country_json}


@app.post('/countries/compare/{country_name_a}/{country_name_b}', status_code=status.HTTP_202_ACCEPTED)
async def compare_countries(country_name_a, country_name_b, background_tasks: BackgroundTasks):
    """Compares two countries for the fields given.

    This actually launches a job as a background task rather than completing and returning a result directly.
    """
    country_a_data, country_b_data = await asyncio.gather(
        get_country_data(country_name_a, response=Response(), filter_names='area,population'),
        get_country_data(country_name_b, response=Response(), filter_names='area,population')
    )
    task_id = str(uuid.uuid4())
    background_tasks.add_task(
        actually_compare_countries, country_a_data, country_b_data, task_id=task_id
    )
    return {"Task ID": task_id}


async def actually_compare_countries(country_a_data: dict, country_b_data: dict, task_id: str):
    # Create task in DB
    tasks: Collection = country_db.tasks
    tasks.insert_one({"Task ID": task_id, "Status": "Running", "Result": None})
    result = {}
    try:
        for key in country_a_data['Data']:
            if isinstance(country_a_data['Data'][key], (int, float)):
                if country_a_data['Data'][key] > country_b_data['Data'][key]:
                    result[key] = country_a_data['Name']
                else:
                    result[key] = country_b_data['Name']
        tasks.update_one({"Task ID": task_id}, {'$set': {'Status': "Completed", "Result": result}})
    except Exception as e:
        tasks.update_one({"Task ID": task_id}, {'$set': {'Status': "Failed"}})


@app.get('/countries/compare/result/{task_id}')
async def get_comparison_results(task_id: str):
    tasks: Collection = country_db.tasks
    task = tasks.find_one({"Task ID": task_id})
    task.pop('_id')
    return task


def search_json_response_for_country(api_response: dict, countries: Collection, country_name: str):
    for country_json in api_response.json():
        if country_json['name']['common'] == country_name:
            countries.insert_one(country_json)
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
        # Get & possibly create the first level dict
        if len(name_group) == 1:
            temp = results
        else:
            temp = results[name_group[0]]
        # Walk through & possibly create dicts to the level with the actual data
        for subkey in name_group[1: -1]:
            temp = temp[subkey]
        # Copy over the data from the main dict
        temp[name_group[-1]] = reduce(lambda x, y: x.get(y, {}), name_group, data)

    return results




if __name__ == "__main__":
    asyncio.run(serve(app, Config()))
