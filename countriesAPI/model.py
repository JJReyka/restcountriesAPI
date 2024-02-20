import pydantic
from pydantic import BaseModel

DotSeparated = pydantic.constr(pattern=r"^(\w+.?)+")


class ComparisonModel(BaseModel):
    """A Model to define the post request input for making a comparison"""

    comparators: list[DotSeparated]
