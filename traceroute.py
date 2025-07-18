import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union


class Router:
    def __init__(self, ip: str, hostname: str, rtts: list[float], flags: Optional[list[str]] = None, data: Optional[dict[Any, Any]] = None):
        self.ip: str = ip
        self.hostname: str = hostname
        self.rtts: list[float] = rtts
        self.flags: Optional[list[str]] = flags
        self.data: Optional[dict[Any, Any]] = data

    def __repr__(self):
        return f"Router(ip={self.ip}, hostname={self.hostname}, rtts={self.rtts}, flags={self.flags}, data={self.data})"

    def __str__(self):
        rtt_str = ", ".join(f"{rtt:.2f}ms" for rtt in self.rtts)
        flags_str = f"Flags: {', '.join(self.flags)}" if self.flags else ""
        data_str = str(self.data) if self.data else ""
        return f"Router: {self.ip} ({self.hostname}) [{rtt_str}] {flags_str} {data_str}".strip()

    def to_dict(self):
        router = dict(self.__dict__)
        return router

    @staticmethod
    def from_dict(value: dict[str, Any]):
        return Router(ip=value["ip"], hostname=value["hostname"], rtts=value["rtts"], flags=value.get("flags"), data=value.get("data"))


class Hop:
    def __init__(self, hop_number: int, routers: list[Router]):
        self.hop_number: int = hop_number
        self.routers: list[Router] = routers

    def __repr__(self):
        return f"Hop(hop_number={self.hop_number}, routers={self.routers})"

    def __str__(self):
        router_strs = "\n  ".join(str(router) for router in self.routers)
        return f"Hop {self.hop_number}:\n  {router_strs}"

    def to_dict(self):
        return {
            "step": self.hop_number,
            "routers": [router.to_dict() for router in self.routers]
        }

    @staticmethod
    def from_dict(value: dict[str, Any]):
        return Hop(hop_number=value["step"], routers=[Router.from_dict(router) for router in value["routers"]])


class TracerouteTarget:
    def __init__(self, target: str, queries: int, max_steps: int, ip: Optional[str] = None, data: Optional[dict[Any, Any]] = None):
        self.target: str = target
        self.ip: Optional[str] = ip
        self.queries: int = queries
        self.max_steps: int = max_steps
        self.data: Optional[dict[Any, Any]] = data

    def __repr__(self):
        return f"TracerouteTarget(target={self.target}, ip={self.ip}, data={self.data}, queries={self.queries}, max_steps={self.max_steps})"

    def __str__(self):
        return f"Traceroute Target: {self.target} [q={self.queries}, m={self.max_steps}]" + (f" ({self.ip})" if self.ip else "") + (
            f" {self.data}" if self.data else "")

    def to_dict(self):
        return {
            "target": self.target,
            "ip": self.ip,
            "queries": self.queries,
            "max_steps": self.max_steps,
            "data": self.data
        }

    @staticmethod
    def from_dict(value: dict[str, Any]):
        return TracerouteTarget(
            target=value["target"],
            queries=value["queries"],
            max_steps=value["max_steps"],
            ip=value.get("ip"),
            data=value.get("data")
        )


class TracerouteResult:
    def __init__(self, target: TracerouteTarget, hops: list[Union[Hop, str]], timestamp: Optional[datetime] = None):
        self.target: TracerouteTarget = target
        self.timestamp: Optional[datetime] = timestamp
        self.hops: list[Union[Hop, str]] = hops

    def __repr__(self):
        return f"TracerouteResult(target={self.target}, hops={self.hops}, timestamp={self.timestamp})"

    def __str__(self):
        hop_strs = "\n".join(str(hop) for hop in self.hops)
        return f"Traceroute Result for {self.target} (Timestamp: {self.timestamp}):\n{hop_strs}"

    def to_dict(self):
        return {
            "target": self.target.to_dict(),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "hops": [hop.to_dict() for hop in self.hops]
        }

    @staticmethod
    def from_dict(value: dict[str, Any]):
        return TracerouteResult(
            target=TracerouteTarget.from_dict(value["target"]),
            hops=[Hop.from_dict(hop) for hop in value["hops"]],
            timestamp=datetime.fromisoformat(value.get("timestamp")) if value.get("timestamp") else None
        )


class Protocol(Enum):
    TCP = "-T",
    UDP = "-U",
    ICMP = "-I"


# Inspired by jc (MIT licensed under https://github.com/kellyjonbrazil/jc/blob/master/LICENSE.md)
REGEX_NAME_AND_IP = re.compile(r'(\S+)\s+\((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|[0-9a-fA-F:]+)\)+')
REGEX_HOP = re.compile(r'^\s*(\d+)?\s+(.+)$')
REGEX_RTT_AND_FLAGS = re.compile(r'(\d+(?:\.?\d+)?)\s+ms\s*(!\S*)?')


def _traceroute(target: str, queries: int, max_steps: int, protocol: Protocol) -> Optional[str]:
    cmd = ["traceroute", "-q", str(queries), "-m", str(max_steps), protocol.value[0], target]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        if "Operation not permitted" in e.stderr:
            raise PermissionError("Traceroute requires root privileges. Please run as root or use sudo.") from e
        if "Name or service not known" in e.stderr:
            raise ValueError(f"Invalid target: {target}.") from e
        raise RuntimeError(f"Traceroute command failed: {e.stderr.strip()}") from e
    except Exception as e:
        raise RuntimeError(f"An error occurred while running traceroute: {str(e)}") from e


def _get_routers(hop_string: str) -> list[Router]:
    if not hop_string.replace("*", "").strip():
        return []

    routers: dict[tuple[str, str], Router] = defaultdict(lambda: Router(ip="", hostname="", rtts=[]))
    parts = REGEX_NAME_AND_IP.split(hop_string)

    for i in range(1, len(parts), 3):
        hostname = parts[i]
        ip = parts[i + 1]
        rtt_data = parts[i + 2] if (i + 2) < len(parts) else ""

        router = routers[(hostname, ip)]
        router.ip = ip
        router.hostname = hostname

        for match in REGEX_RTT_AND_FLAGS.finditer(rtt_data):
            if match.group(1):
                router.rtts.append(float(match.group(1)))
            if match.group(2):
                if not router.flags:
                    router.flags = []
                router.flags.append(match.group(2).strip("!"))

    return list(routers.values())


def traceroute(target: str, queries: int = 3, max_steps: int = 30, protocol: Protocol = Protocol.TCP) -> TracerouteResult:
    """
    Traces the route to the target using the traceroute command and returns the result
    :param target: The target to trace the route to
    :param queries: The amount of queries to send
    :param max_steps: The maximum amount of hops to trace
    :param protocol: The protocol to use for the traceroute (TCP, UDP, ICMP)
    :return: TracerouteResult containing the target, hops, and timestamp
    """
    lines = _traceroute(target, queries, max_steps, protocol).splitlines()
    timestamp = datetime.now()
    header = lines[0].strip()
    hop_lines = lines[1:]

    destination_match = REGEX_NAME_AND_IP.search(header)
    if not destination_match or len(destination_match.groups()) != 2:
        raise ValueError(f"Invalid traceroute output header: {header}")

    target, target_ip = destination_match.groups()
    hops = []

    for line in hop_lines:
        if not line.strip():
            continue

        hop_match = REGEX_HOP.match(line)
        if not hop_match or len(hop_match.groups()) != 2:
            raise ValueError(f"Invalid hop line format: {line}")

        index = int(hop_match.group(1)) if hop_match.group(1) else None
        content = hop_match.group(2)

        routers = _get_routers(content)

        if not routers:
            continue

        hops.append(Hop(hop_number=index, routers=routers))

    return TracerouteResult(
        target=TracerouteTarget(target=target, ip=target_ip, queries=queries, max_steps=max_steps),
        hops=hops,
        timestamp=timestamp
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Traceroute options')

    parser.add_argument('--queries', type=int, default=3, help='Number of queries per hop (default: 3)')
    parser.add_argument('--max-steps', type=int, default=30, help='Maximum number of hops (default: 30)')
    parser.add_argument('--protocol', type=lambda p: Protocol[p] if p in Protocol.__members__ else Protocol.TCP, default=Protocol.TCP, choices=list(Protocol), help='Protocol to use for traceroute (TCP, UDP, ICMP; default: TCP)')
    parser.add_argument('--threads', type=int, default=1, help='Number of concurrent threads (default: 1)')

    args = parser.parse_args()

    if args.threads > 1:
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = [
                executor.submit(traceroute, target.strip(), queries=args.queries, max_steps=args.max_steps, protocol=args.protocol) for target in sys.stdin if target.strip()
            ]

            for future in as_completed(futures):
                try:
                    result = future.result()
                    print(json.dumps(result.to_dict(), separators=(',', ':')))
                except Exception as e:
                    print("Error:", str(e), file=sys.stderr)
    else:
        for target in sys.stdin:
            target = target.strip()
            if not target:
                continue

            try:
                result = traceroute(target, queries=args.queries, max_steps=args.max_steps, protocol=args.protocol)
                print(json.dumps(result.to_dict(), separators=(',', ':')))
            except Exception as e:
                print("Error:", str(e), file=sys.stderr)
