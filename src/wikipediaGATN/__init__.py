# __init__.py for wikipediaGATN package


import requests
from bs4 import BeautifulSoup
import re
import time
import os
import json
import urllib.parse

# Define the package version
__version__ = "0.1.0"