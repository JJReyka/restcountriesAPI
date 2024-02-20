"""Programmatically check actual api calls. You can do this with the openAPI ui in browser
but this isn't the best for 2 part requests"""
import requests


def comparison_request(country_a, country_b):
    response = requests.post(f"http://127.0.0.1:8000/countries/compare/{country_a}/{country_b}")
    task_id = response.json().get('Task ID')
    while response.json().get('Status') not in ['Completed', 'Failed'] and task_id is not None:
        response = requests.get(f"http://127.0.0.1:8000/countries/compare/result/{task_id}")
        print(response.json().get('Status'), response.json()['Result'])

if __name__ == "__main__":
    comparison_request('United States', 'Japan')