import argparse
from typing import Any

from targets import SERVER_DICT, Service
from fanout import server_roundtrip, parsed_server_roundtrip
from http1 import remove_request_header, HTTPRequest, HTTPResponse


def allows_http_0_9(server: Service) -> bool:
    response_stream: list[bytes] = server_roundtrip([b"GET /\r\n\r\n"], server)
    assert len(response_stream) == 1 or print(server.name, response_stream)
    response: bytes = b"".join(response_stream)
    eol: int = response.find(b"\n")
    if eol == -1:
        eol = len(response)
    return len(response) > 0 and b"400" not in response[:eol]


def get_added_headers(server: Service) -> list[tuple[str, str]]:
    pts, _ = parsed_server_roundtrip([b"GET / HTTP/1.1\r\nHost: a\r\n\r\n"], server, traced=False)
    result: list[tuple[str, str]] = []

    assert len(pts) == 1 or print(server.name, pts)
    pt = pts[0]
    assert isinstance(pt, HTTPRequest) or print(server.name, pt)
    pt = remove_request_header(pt, b"host")

    result += [(k.decode("latin1"), v.decode("latin1")) for k, v in pt.headers]

    pts, _ = parsed_server_roundtrip([b"GET / HTTP/1.1\r\n\r\n"], server, traced=False)

    if len(pts) > 0 and isinstance(pts[0], HTTPRequest):
        pt = pts[0]
        result += [(k.decode("latin1"), v.decode("latin1")) for k, v in pt.headers]

    return result


def translates_chunked_to_cl(server: Service) -> bool:
    pts, _ = parsed_server_roundtrip(
        [b"POST / HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"], server, traced=False
    )
    assert len(pts) == 1 or print(server.name, pts)
    pt = pts[0]
    assert isinstance(pt, HTTPRequest) or print(server.name, pt)
    return pt.has_header(b"content-length")


def requires_length_in_post(server: Service) -> bool:
    pts, _ = parsed_server_roundtrip([b"POST / HTTP/1.1\r\nHost: a\r\n\r\n"], server, traced=False)
    assert len(pts) == 1 or print(server.name, pts)
    return isinstance(pts[0], HTTPResponse)


def allows_missing_host_header(server: Service) -> bool:
    pts, _ = parsed_server_roundtrip([b"GET / HTTP/1.1\r\n\r\n"], server, traced=False)
    assert len(pts) == 1 or print(server.name, pts)
    return isinstance(pts[0], HTTPRequest)


def get_header_name_translation(server: Service) -> dict[str, str]:
    pts, _ = parsed_server_roundtrip([b"GET / HTTP/1.1\r\nHost: a\r\na-b: a-b\r\n\r\n"], server, traced=False)
    assert len(pts) == 1 or print(server.name, pts)
    pt = pts[0]
    assert isinstance(pt, HTTPRequest) or print(server.name, pt)
    return {"-": "_"} if pt.has_header(b"a_b") else {}


def doesnt_support_version(server: Service) -> bool:
    pts1, _ = parsed_server_roundtrip([b"GET / HTTP/1.1\r\nHost: a\r\n\r\n"], server, traced=False)
    assert len(pts1) == 1 or print(server.name, pts1)
    pt1 = pts1[0]
    assert isinstance(pt1, HTTPRequest)

    pts2, _ = parsed_server_roundtrip([b"GET / HTTP/1.0\r\nHost: a\r\n\r\n"], server, traced=False)
    assert len(pts2) == 1 or print(server.name, pts2)
    pt2 = pts2[0]
    assert isinstance(pt2, HTTPRequest)

    return pt1.version == pt2.version


def joins_duplicate_headers(server: Service) -> bool:
    pts, _ = parsed_server_roundtrip(
        [b"GET / HTTP/1.1\r\nHost: a\r\na: A\r\na: B\r\n\r\n"], server, traced=False
    )
    assert len(pts) == 1 or print(server.name, pts)
    pt = pts[0]
    assert isinstance(pt, HTTPRequest)

    return pt.has_header(b"a", b"A, B") or pt.has_header(b"a", b"A,B")


def main() -> None:
    arg_parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="This script tests the specified servers for a number of common HTTP parsing quirks that are usually considered benign. Its output can be used in `anomalies.yml` so that these benign discrepancies can be ignored."
    )
    arg_parser.add_argument(
        "--servers",
        default=None,
        help="Comma-separated list of server names from docker-compose.yml.",
    )
    arg_parser.add_argument(
        "--all",
        action="store_true",
        help="Whether to use all endpoints, instead of just those specified with --servers.",
    )

    args: argparse.Namespace = arg_parser.parse_args()

    servers: list[Service] = (
        list(SERVER_DICT.values())
        if args.all
        else [SERVER_DICT[s] for s in args.servers.split(",") if len(s) > 0]
        if args.servers is not None
        else []
    )
    print(",".join([s.name for s in servers]))

    for server in servers:
        anomalies: dict[str, Any] = {}
        if allows_http_0_9(server):
            anomalies["allows-http-0-9"] = "true"
        added_headers = get_added_headers(server)
        if len(added_headers) > 0:
            anomalies["added-headers"] = [list(h) for h in added_headers]
        if translates_chunked_to_cl(server):
            anomalies["translates-chunked-to-cl"] = "true"
        if requires_length_in_post(server):
            anomalies["requires-length-in-post"] = "true"
        if allows_missing_host_header(server):
            anomalies["allows-missing-host-header"] = "true"
        header_name_translation = get_header_name_translation(server)
        if len(header_name_translation) > 0:
            anomalies["header-name-translation"] = header_name_translation
        if doesnt_support_version(server):
            anomalies["doesnt-support-version"] = "true"

        if len(anomalies) > 0:
            print(f"{server.name}:")
        for k, v in anomalies.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
