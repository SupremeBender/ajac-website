#!/bin/bash
source /var/www/beta.ajac.no/.venv/bin/activate
# Start disc_bot.py in the background
python /var/www/beta.ajac.no/disc_bot.py &
# Start Flask app in the foreground
python /var/www/beta.ajac.no/app.py