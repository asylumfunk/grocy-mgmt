from os import environ

from grocy.grocy_api_client import DEFAULT_PORT_NUMBER
from grocy import Grocy


API_HOST = environ['GROCY_API_HOST']
API_PORT = environ.get('GROCY_API_PORT', DEFAULT_PORT_NUMBER)
API_KEY = environ['GROCY_API_KEY']
grocy = Grocy(API_HOST, API_KEY, port=API_PORT)
