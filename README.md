# ⚒️ Paul's Tool Collection

A collection of tools and scripts for various (networking) tasks.

### Traceroute
A python wrapper for traceroute taking targets as input and returning the results in json format.

```bash
echo "1.1.1.1" | python3 traceroute.py --queries 3 --max_steps 30 --threads 1 --protocol TCP
```

Currently, only Van Jacobson's (Modern) traceroute is supported.
If more than one thread is configured, the script will run traceroutes in parallel.

### Geolocation

A python script to geolocate IP addresses using [MaxMinds City](https://dev.maxmind.com/geoip/docs/databases/city-and-country/) database.

```bash
# Install dependencies
pip install pytricia

# Generate the database from the MaxMind CSV files
python3 geolocate.py setup

# Geolocate an IP address
echo "49.13.113.19" | python3 geolocate.py query
```

