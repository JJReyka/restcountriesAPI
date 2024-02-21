"""Programmatically check actual api calls. You can do this with the openAPI ui in browser
but this isn't the best for 2 part requests"""
import requests
import grequests


def comparison_request(country_a, country_b, compare):
    response = requests.post(
        f"http://127.0.0.1:8000/countries/compare/{country_a}/{country_b}", json={'comparators': compare}
    )
    task_id = response.json().get('task_id')
    while response.json().get('status') not in ['Completed', 'Failed'] and task_id is not None:
        response = requests.get(f"http://127.0.0.1:8000/countries/compare/result/{task_id}")
        print(response.json().get('status'), response.json()['result'])


def compare_to_belgium():
    """Check to see if async requests get handled ok by the server."""
    urls = [
        f"http://127.0.0.1:8000/countries/compare/{country}/Belgium"
        for country in ['Spain', 'Italy', 'France', 'Luxembourg', 'Greenland']
    ]
    rs = (grequests.post(u, json={'comparators': ['area', 'population']}) for u in urls)
    res = grequests.map(rs)
    urls = []
    for r in res:
        task_id = r.json()['task_id']
        urls.append(f"http://127.0.0.1:8000/countries/compare/result/{task_id}")
    rs = (grequests.get(u) for u in urls)
    res = grequests.map(rs)
    for r in res:
        print(r.json())


if __name__ == "__main__":
    comparison_request('Spain', 'Canada', ['area', 'population'])
    compare_to_belgium()