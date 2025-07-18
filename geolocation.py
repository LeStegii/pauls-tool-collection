import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional, Any

from pytricia import PyTricia


class GeoLocation:
    def __init__(self, lat: Optional[float], lon: Optional[float], continent: Optional[str], country: Optional[str], city: Optional[str], accuracy_radius: Optional[int] = None):
        self.lat: Optional[float] = lat
        self.lon: Optional[float] = lon
        self.continent: Optional[str] = continent
        self.country: Optional[str] = country
        self.city: Optional[str] = city
        self.accuracy_radius: Optional[int] = accuracy_radius

    def __repr__(self):
        return f"GeoLocation(lat={self.lat}, lon={self.lon}, continent={self.continent}, country={self.country}, city={self.city}, accuracy_radius={self.accuracy_radius})"

    def __str__(self):
        location_parts = [self.city, self.country, self.continent]
        location_str = ", ".join(filter(None, location_parts))
        coords = f"({self.lat}, {self.lon})" if self.lat is not None and self.lon is not None else ""
        return f"{location_str} {self.accuracy_radius} {coords}".strip()

    def to_dict(self):
        return self.__dict__

    @staticmethod
    def from_dict(value: dict[str, Any]):
        return GeoLocation(lat=value.get("lat"), lon=value.get("lon"), continent=value.get("continent"), country=value.get("country"), city=value.get("city"), accuracy_radius=value.get("accuracy_radius"))


def geoloc(ip: str, trie: PyTricia) -> Optional[GeoLocation]:
    if not ip:
        return None

    # Add leading and trailing zeros to IPv6 addresses (https://github.com/jsommers/pytricia/issues/34#issuecomment-1112043167)
    ip = f"0{ip}" if ip.startswith("::") else ip
    ip = f"{ip}0" if ip.endswith("::") else ip

    return trie.get(ip)


def construct_trie(locations: Path, blocks: list[Path]) -> PyTricia:
    for block in blocks:
        if not block.is_file():
            raise ValueError(f"Block file {block} is not a file")
    if not locations.is_file():
        raise ValueError(f"Locations file {locations} is not a file")

    prefixes: dict[str, tuple[int, float, float, int]] = {}  # prefix -> (geo_id, lat, lon, accuracy_radius)

    for block in blocks:
        with open(block) as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                try:
                    # network,geoname_id,registered_country_geoname_id,represented_country_geoname_id,is_anonymous_proxy,is_satellite_provider,postal_code,latitude,longitude,accuracy_radius,is_anycast
                    prefix = row[0]
                    geo_id = int(row[1]) if row[1] else None
                    lat = float(row[7]) if row[7] else None
                    lon = float(row[8]) if row[8] else None
                    accuracy_radius = int(row[9]) if row[9] else None
                    prefixes[prefix] = (geo_id, lat, lon, accuracy_radius)
                except ValueError:
                    print(f"Error parsing row: {row}", file=sys.stderr)
                    continue

    cities: dict[int, tuple[str, str, str]] = {}  # geo_id -> (continent_code, country_code, city)

    with open(locations) as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            try:
                # geoname_id,locale_code,continent_code,continent_name,country_iso_code,country_name,subdivision_1_iso_code,subdivision_1_name,subdivision_2_iso_code,subdivision_2_name,city_name,metro_code,time_zone,is_in_european_union
                geo_id = int(row[0])
                continent_code = row[2]
                country_code = row[4]
                city = row[10]
                cities[geo_id] = (continent_code, country_code, city)
            except ValueError:
                print(f"Error parsing row: {row}", file=sys.stderr)
                continue

    trie = PyTricia()
    for prefix, (geo_id, lat, lon, accuracy_radius) in prefixes.items():
        if geo_id and geo_id in cities:
            continent_code, country_code, city = cities[geo_id]
            continent = continent_code
            country = country_code
            city = city
        else:
            continent = None
            country = None
            city = None

        location = GeoLocation(lat=lat, lon=lon, continent=continent, country=country, city=city, accuracy_radius=accuracy_radius)
        trie.insert(prefix, location)

    return trie


def export_trie(trie: PyTricia, output_file: Optional[Path] = None):
    if output_file:
        with open(output_file, "w") as f:
            for prefix in trie.keys():
                location = trie.get(prefix)
                f.write(f"{prefix},{json.dumps(location.to_dict(), separators=(",", ":"))}\n")
    else:
        for prefix in trie.keys():
            print(f"{prefix},{json.dumps(trie.get(prefix).to_dict(), separators=(",", ":"))}")


def import_trie(input_file: Path) -> PyTricia:
    trie = PyTricia()
    with open(input_file, "r") as f:
        for line in f:
            prefix, location_json = line.strip().split(",", 1)
            location = GeoLocation.from_dict(json.loads(location_json))
            trie.insert(prefix, location)
    return trie


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Geolocation Options")

    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Build the mapping trie from CSV files.")
    setup_parser.add_argument("locations", nargs="?", type=Path, help="Path to the locations CSV file.")
    setup_parser.add_argument("blocks", nargs="*", type=Path, help="Paths to the blocks CSV files.")
    setup_parser.add_argument("--output", type=Path, default=Path("geoloc.trie"), help="Output trie file to (default: geoloc.trie)")

    query_parser = subparsers.add_parser("query", help="Query using a previously built trie.")
    query_parser.add_argument("--input", type=Path, default=Path("geoloc.trie"), help="Input trie file to query against (default: geoloc.trie)")

    args = parser.parse_args()

    if args.command == "setup":
        locations = args.locations or Path("GeoLite2-City-Locations-en.csv")
        blocks = args.blocks if args.blocks else [Path("GeoLite2-City-Blocks-IPv4.csv"), Path("GeoLite2-City-Blocks-IPv6.csv")]
        trie = construct_trie(locations, blocks)
        export_trie(trie, args.output)
    elif args.command == "query":

        trie = import_trie(args.input)

        for ip in sys.stdin:
            ip = ip.strip()
            location = geoloc(ip, trie)
            if location:
                print(json.dumps({"ip": ip, "location": location.to_dict()}, separators=(",", ":")))
            else:
                print(f"No location found for IP: {ip}", file=sys.stderr)
    else:
        parser.print_help()
        sys.exit(1)
