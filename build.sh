#!/bin/bash
set -o errexit
pip install -r requirements.txt
python manage.py migrate
python manage.py createcachetable
python manage.py collectstatic --noinput
