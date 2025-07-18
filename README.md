# ⚒️ Paul's Tool Collection

A collection of tools and scripts for various (networking) tasks.

### Traceroute
A python wrapper for traceroute taking targets as input and returning the results in json format.

```bash
echo "1.1.1.1" | python3 traceroute.py --queries 3 --max_steps 30 --threads 1 --protocol TCP
```

Currently, only Van Jacobson's (Modern) traceroute is supported.
If more than one thread is configured, the script will run traceroutes in parallel.

Every argument is optional, the defaults are displayed in the command above.

### Geolocation

A python script to geolocate IP addresses using [MaxMinds City](https://dev.maxmind.com/geoip/docs/databases/city-and-country/) database.

```bash
# Install dependencies
pip install pytricia

# Generate the database from the MaxMind CSV files
python3 geolocate.py setup --output geoloc.trie

# Geolocate an IP address
echo "49.13.113.19" | python3 geolocate.py query --input geoloc.trie
```

For setting up the databases, the CSV files from MaxMind are required. Per default, the script expected the location file (e.g. `GeoLite2-City-Locations-en.csv`) and the block file(s) (e.g. `GeoLite2-City-Blocks-IPv4.csv`, `GeoLite2-City-Blocks-IPv6.csv`) to be in the same directory as the script.
This can be changed by putting the location and block files as arguments behind the `setup` command.
Additionally, the output file can be changed by using `--output <file>`, same for the `query` command with `--input <file>` (defaults to `geoloc.trie`).