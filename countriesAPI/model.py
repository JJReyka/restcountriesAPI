"""Data models for requests and responses"""

import pydantic
from pydantic import BaseModel

DotSeparated = pydantic.constr(pattern=r"^(\w+.?)+\w")


class ComparisonModel(BaseModel):
    """A Model to define the post request input for making a comparison"""

    comparators: list[DotSeparated]


class CountryDataModel(BaseModel):

    name: str
    data: dict | None
    message: str | None = None


class TaskCreationModel(BaseModel):

    task_id: str | None
    message: str


class TaskStatusModel(BaseModel):

    task_id: str
    status: str
    result: dict | None
