from airflow import DAG
from airflow.providers.http.hooks.http import HttpHook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.decorators import task
from pendulum import datetime
import requests
import json

# Latitude and longitude for the location
LATITUDE = '40.7128'  # Example: New York City
LONGITUDE = '-74.0060'
POSTGRES_CONNECTION_ID = 'postgres_default'
API_CONNECTION_ID = 'open_meteo_api'

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2025, 7, 2, tz="UTC"),
}

# Define the DAG
with DAG(dag_id='weather_etl_pipeline',
         default_args=default_args,
         schedule='@daily',
         catchup=False) as dag:
    @task()
    def extract_weather_data():
        """ Extract weather data from Open-Meteo API """
        # Use HttpHook to make a GET request to the Open-Meteo API
        http_hook = HttpHook(method='GET', http_conn_id=API_CONNECTION_ID)
        # Construct the API endpoint with latitude and longitude
        # https://api.open-meteo.com/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current_weather=true
        endpoint = f'/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current_weather=true'
        # Make the request and return the JSON response
        response = http_hook.run(endpoint)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to fetch data: {response.status_code} {response.text}")
        
    @task()
    def transform_weather_data(weather_data):
        """ Transform the weather data to extract relevant fields """
        # Extract the current weather information
        current_weather = weather_data['current_weather']
        transformed_data = {
            'latitude': LATITUDE,
            'longitude': LONGITUDE,
            'temperature': current_weather['temperature'],
            'windspeed': current_weather['windspeed'],
            'winddirection': current_weather['winddirection'],
            'weathercode': current_weather['weathercode'],
            'time': current_weather['time'],
        }
        return transformed_data 
    
    @task()
    def load_weather_data(transformed_data):
        """ Load the transformed data into PostgreSQL """
        # Use PostgresHook to connect to PostgreSQL
        pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONNECTION_ID)
        conn = pg_hook.get_conn()
        cursor = conn.cursor()
        
        # Create the table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weather_data (
                latitude FLOAT,
                longitude FLOAT,
                temperature FLOAT,
                windspeed FLOAT,
                winddirection FLOAT,
                weathercode INT,
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Insert the transformed data into the table
        cursor.execute("""
        INSERT INTO weather_data (latitude, longitude, temperature, windspeed, winddirection, weathercode, time)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,(
            transformed_data['latitude'],
            transformed_data['longitude'],
            transformed_data['temperature'],
            transformed_data['windspeed'],
            transformed_data['winddirection'],
            transformed_data['weathercode'],
            transformed_data['time']
        ))
        conn.commit()
        cursor.close()
        
    # DAG workflow
    weather_data = extract_weather_data()
    transformed_data = transform_weather_data(weather_data)
    load_weather_data(transformed_data)