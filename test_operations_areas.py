import os
import sys
import json
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Print the directory structure for theaters
config_dir = os.path.join(os.path.dirname(__file__), "instance/data")
theaters_dir = os.path.join(config_dir, "theatres")
print(f"Looking for theaters in: {theaters_dir}")
print(f"Directory exists: {os.path.exists(theaters_dir)}")
print(f"Is directory: {os.path.isdir(theaters_dir)}")

if os.path.exists(theaters_dir) and os.path.isdir(theaters_dir):
    print("Theater files:")
    for filename in os.listdir(theaters_dir):
        print(f"  - {filename}")

# Import the function to test
from utils.resources import get_operations_areas

# Test the function
operations_areas = get_operations_areas()

# Print the result
print("\nOperations Areas:")
print(json.dumps(operations_areas, indent=2))

# Check if the fix works
if operations_areas:
    print("\nFix successful! Found operations areas:", len(operations_areas))
else:
    print("\nFix failed! No operations areas found.")
