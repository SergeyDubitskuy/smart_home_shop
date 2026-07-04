import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_smart_home_secret')
    PG_DSN = "dbname=smart_home_db user=postgres password=123123 host=localhost"
    MONGO_URI = "mongodb://localhost:27017/"