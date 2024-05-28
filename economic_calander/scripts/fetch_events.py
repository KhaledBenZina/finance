import requests

def fetch_economic_events():
    url = "https://financialmodelingprep.com/api/v3/economic_calendar"
    params = {
        'apikey': 'e3ea76a31e98cfd50753c06e3980f9a8'  # Replace 'YOUR_API_KEY' with your actual Financial Modeling Prep API key
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"Other error occurred: {err}")



if __name__ == "__main__":
    print(fetch_economic_events())