import requests
import datetime
import csv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time

client_id = '...'
client_secret = '...'

# Get access token
def get_spotify_access_token():
    print("Getting access token...")
    
    auth_url = 'https://accounts.spotify.com/api/token'
    try:
        auth_response = requests.post(auth_url, {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
        })
        if auth_response.status_code == 200:
            response_access_token = auth_response.json()['access_token']
            print("Access token retrieved successfully: ", response_access_token)
            return response_access_token
        else:
            print(f"Failed to get access token: {auth_response.status_code} - {auth_response.text}")
            return None
    except Exception as e:
        print(f"Error during token retrieval: {e}")
        return None
    
# Find related spotify shows/podcasts to a query
def get_spotify_show_ids(query, access_token, existing_ids, offset):
    url = "https://api.spotify.com/v1/search"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "q": query,
        "market": "US",
        "type": "show",
        "limit": 40,
        "offset": offset
    }

    new_show_ids = []

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        shows = data.get('shows', {}).get('items', [])

        for show in shows:
            show_id = show.get('id')
            # show_name = show.get('name', 'Unknown Show')

            if (show_id and show_id not in existing_ids) and (show_id and show_id not in new_show_ids):
                new_show_ids.append(show_id)
    else:
        print(f"Failed to retrieve data: {response.status_code}")

    return new_show_ids
    
# Get details of a show
def get_show_details(show_id, access_token):
    endpoint = f"https://api.spotify.com/v1/shows/{show_id}"
    try:
        response = requests.get(endpoint, headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to get show details: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching show details: {e}")
        return None

# Get 10 most recent episodes of a show
def get_show_episodes(show_id, access_token, limit=10):
    endpoint = f"https://api.spotify.com/v1/shows/{show_id}/episodes?limit={limit}"
    try:
        response = requests.get(endpoint, headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to get show episodes: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching show episodes: {e}")
        return None

def disable_css(driver):
    # JavaScript to disable all stylesheets (not sure if this provides any substantial performance boost though)
    disable_css_script = """
    for (let i = 0; i < document.styleSheets.length; i++) {
        document.styleSheets[i].disabled = true;
    }
    """
    driver.execute_script(disable_css_script)

# Scrape and find the Spotify ratings
def scrape_spotify_ratings(driver, show_id):
    # Open the URL
    driver.get("https://open.spotify.com/show/" + show_id)
    disable_css(driver)

    # Wait for JavaScript to load
    time.sleep(10)

    # Scrape the data
    try:
        rating_div = driver.find_element(By.CLASS_NAME, "urKYEVZPj2k0hwDT1qzt")
        rating_avg = rating_div.find_element(By.CLASS_NAME, "Type__TypeElement-sc-goli3j-0.eoWRdH").text
        num_of_raters = rating_div.find_element(By.CLASS_NAME, "Type__TypeElement-sc-goli3j-0.ieTwfQ").text.strip('()')
        
        print(f"Rating: {rating_avg} - {num_of_raters}")
        
    except Exception as e:
        print("Error scraping Spotify ratings")
        return "N/A", "N/A"

    return rating_avg, num_of_raters
    
# Process a Spotify show
def process_spotify_show(driver, show_id, access_token):
    show_details = get_show_details(show_id, access_token)
    if not show_details:
        return None
    
    # Extract copyright details
    copyright_texts = [copyright.get('text', '') for copyright in show_details.get('copyrights', [])]

    # Extract details
    data = {
        'Name': show_details['name'],
        'Description': show_details['description'],
        'Copyright': ', '.join(copyright_texts),
        'Languages': ', '.join(show_details['languages']),
        'Is Explicit?': show_details['explicit'],
        'Publisher': show_details['publisher'],
        'Externally Hosted?': show_details['is_externally_hosted'],
        'Total # Episodes': show_details['total_episodes'],
        'Link': f"https://open.spotify.com/show/{show_id}"
    }

    # Get episodes
    episodes = get_show_episodes(show_id, access_token)

    # Calculate average episode length and average distance between episodes
    episode_lengths = [episode['duration_ms'] for episode in episodes['items']]
    data['Average Episode Length (minutes)'] = round(sum(episode_lengths) / len(episode_lengths) / 60000, 2)

    # Parse average release date
    release_dates = []
    for episode in episodes['items']:
        if episode['release_date_precision'] == 'day':
            try:
                release_date = datetime.datetime.fromisoformat(episode['release_date'])
                release_dates.append(release_date)
            except ValueError:
                print(f"Invalid release date format for episode: {episode['name']}")

    # Calculate average distance between episodes
    if len(release_dates) > 1:
        date_differences = [(release_dates[i] - release_dates[i+1]).days for i in range(len(release_dates)-1)]
        data['Average Distance Between Episodes (days)'] = round(sum(date_differences) / len(date_differences), 2)
    else:
        data['Average Distance Between Episodes (days)'] = 'N/A'

    # rating, num_of_raters = scrape_spotify_ratings(driver, show_id)
    # data['Rating'] = rating
    # data['Number of Raters'] = num_of_raters
    data['Rating'] = 0
    data['Number of Raters'] = 0

    return data

# Refresh token every 20 iterations
def refresh_token_if_needed(i, access_token):
    if (i + 1) % 20 == 0:
        print("Refreshing access token...")
        return get_spotify_access_token()
    return access_token

def generate_csv(data, filename):
    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        for row in data:
            if row:  # Ensure row is not None
                dict_writer.writerow(row)

# Get access token
access_token = get_spotify_access_token()

# Shows to process
spotify_show_ids = [
    '4xqcgyQkZMzZSXkSwXYR5T',
    '4cFYKWTiOzAMP0QQC0Mwkx',
    '0sNdBa0Na1r675cHzhQJPz',
    '6j3gZDkp7ZCxN26si3Ajvp',
    '6FCpvu4nSptKgwhg5NMmJ9',
    '4TR7TQBAQvUQWIpYlf2uXv',
    '0u407iIKhT41WuzaG4UG1x',
    '7bcyVhpdhw0hbiRr6O4h1U',
    '6zlcXgcd2kX9E4cbQTCsR9',
    '6d9s4PBzvdESARqUadlCpo',
    '40bu5CZXwlMoXRY9AWtAyD',
    '1bJRgaFZHuzifad4IAApFR',
    '18mQoogq5SccoxF0RRw6s0',
    '4Ak6HpbVkLKGacY3E0GHL8',
    '7EEOkGGhmVnqHY4CNNrZDv',
    '3yM6oR3QD2chAFdSXAgzzK',
    '1bwnEYfxwuDxT20OEQF5ZL',
    '7rZaCLqd8otZmJjmC8squm',
    '4AFHekKU9OMJnS0GLSG5sX',
    '6rNgMnwpGO0AvstorH7bbK',
    '7pv0JHF2YGgXm8OGz1JnL0',
    '1XBrhVLsQOIAv3KFBqnzrX',
    '5qoM5evv8FUvaqkSY6OHzn',
    '5mt9FHLE7MbsuUjH4YNx7T',
    '4PMEce8Hs2Z5RNwgE4vepN',
    '5wqbB4mm1LXCbD4wiy8oef',
    '3lYikBXFrfp3Y7EQlXojrc',
    '2SmX6lTUIhYpsWqhEa6k4W',
    '1Z2HZISdr7K97uWmlPOlDH',
    '1V4mGgp5SAeMOwPP8lQYkx',
    '3gkEHPos4NIkmAYIQnXzDM',
    '3TV1jXZqlSFCzZ3xqvcG96',
    '0G5ngjojeBAWqWqQHcDlLA',
    '6pXRLZtbexN9ObpQRa06SJ',
    '2dR1MUZEHCOnz1LVfNac0j',
    '46rn9PQrL1JGcehZ2gT195',
    '6E709HRH7XaiZrMfgtNCun',
    '4r6DQLCHDaSNjbgtZtAfUp',
    '5kcEHIj6RjVMTNBAx3ONVr',
    '6ULQ0ewYf5zmsDgBchlkr9',
    '7qaORTBP1bTnV74qdWZu0j',
    '03zERV3rvMZ58uqueamoFB',
    '2wBDkJDfAX26XwwjS4tCt6',
    '6Wg14aTm1M3YEo38WalND9',
    '0SVk5JPacZMqS1w5lvP0jf',
    '599Pg4sTXDPSJBI8N5spt2',
    '4LFGskcWxENjMPO0V7HNqF',
    '7pv0JHF2YGgXm8OGz1JnL0',
    '20NFvqJOnPKAP7YVpFyswC',
    '21mSaFgOhfR7TT8MKxF41n',
    '6idQBTQNbAQEKSDJHV5OjX',
    '2RmlL4uHpuZKkvdfQktBNO',
    '0XAP6LCThtyRWblrsA4Ihj',
    '5LSozZ9e084KYlylX1Oix1',
    '0b7BW1MSiHAxCsSPRIjq0n'
]

# Generate some extras using Spotify search in case some relevant shows are missing
extra_spotify_show_ids = get_spotify_show_ids("product management", access_token, spotify_show_ids, 0)
extra_spotify_show_ids.extend(get_spotify_show_ids("product management", access_token, spotify_show_ids, 40))

print(f"Number to process: {len(spotify_show_ids)}")
print(f"Number of extra to process: {len(extra_spotify_show_ids)}")

# Set up webcrawler/driver
options = Options()
options.add_argument("--headless=new")

prefs = {
    'profile.managed_default_content_settings.images': 2, # Don't load images
}
options.add_experimental_option('prefs', prefs)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Process each URL and collect the data
start_time = time.time()

collected_data = []
for i, show_id in enumerate(spotify_show_ids):
    print(f"Processing number: {i + 1}")
    access_token = refresh_token_if_needed(i, access_token)
    collected_data.append(process_spotify_show(driver, show_id, access_token))

# # Processing batch of extra spotify shows
# for i, show_id in enumerate(extra_spotify_show_ids):
#     print(f"Processing number: {i + 1}")
#     access_token = refresh_token_if_needed(i, access_token)
#     collected_data.append(process_spotify_show(driver, show_id, access_token))

# End driver
driver.quit()

# Generate CSV
generate_csv(collected_data, "spotify_podcasts.csv") # rename this as needed for different files

end_time = time.time()

# Calculate total runtime
total_runtime = end_time - start_time
print(f"Total Runtime: {total_runtime:.2f} seconds")
