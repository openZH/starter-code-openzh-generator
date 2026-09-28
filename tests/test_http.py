"""Exercise actual HTTP requests against a local fixture server."""

import gzip
import json
import subprocess
import sys
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from textwrap import indent
from threading import Thread

import pandas as pd
import pytest

from starter_code_openzh_generator import updater


@pytest.mark.parametrize("compressed", [False, True], ids=["plain", "gzip"])
def test_generator_and_notebook_send_configured_user_agents(
    tmp_path: Path,
    compressed: bool,
) -> None:
    """Stream CSVs with the configured header and surface HTTP and parsing errors."""
    requests_seen: list[tuple[str, str | None]] = []
    catalogue: dict[str, object] = {}
    data = pd.DataFrame({"a": [1], "b": [2]})
    payload = data.to_csv(index=False).encode()

    class Handler(BaseHTTPRequestHandler):
        """Serve metadata and a tiny CSV without external network access."""

        def do_GET(self) -> None:
            requests_seen.append((self.path, self.headers.get("User-Agent")))
            body = {
                "/catalogue": json.dumps(catalogue).encode(),
                "/selected": payload,
                "/broken": b"a,b\n1,2\n3,4,5\n",
                "/missing": b"a,b\n1,2\n",
            }[self.path]
            self.send_response(404 if self.path == "/missing" else 200)
            if compressed:
                body = gzip.compress(body)
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Suppress fixture access logs."""

    root = Path(__file__).resolve().parents[1]
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}"
        catalogue["dataset"] = [
            {
                "identifier": "1@example",
                "title": "Example",
                "distribution": [
                    {
                        "ktzhDistId": "1",
                        "format": "CSV",
                        "downloadUrl": base + "/selected",
                    },
                    {"ktzhDistId": "2", "format": "CSV", "downloadUrl": base + "/other"},
                ],
            }
        ]
        config = replace(
            updater.Config.from_yaml(root / "config.yaml"),
            template_folder=root / "_templates",
            temp_prefix=tmp_path / "output",
            metadata_link=base + "/catalogue",
            user_agent_generator="Generator-Test/1",
            user_agent_python="Notebook-Test/1",
            user_agent_r="R-Test/1",
        )
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            updater.run_update(config)
            assert requests_seen == [("/catalogue", "Generator-Test/1")]
            manifest = json.loads((config.temp_prefix / "manifest.json").read_text())
            entry = manifest["resource_files"][0]
            notebook = json.loads((config.temp_prefix / entry["python"]).read_text())
            cells = {c.get("id"): "".join(c["source"]) for c in notebook["cells"]}
            script = tmp_path / "load.py"
            checks = (
                cells["distributions"]
                + "\nassert df.to_dict('list') == {'a': [1], 'b': [2]}\n"
                + "with pytest.raises(requests.HTTPError) as error:\n"
                + f"    get_dataset({base + '/missing'!r})\n"
                + "assert error.value.response.status_code == 404\n"
                + "with pytest.raises(pd.errors.ParserError):\n"
                + f"    get_dataset({base + '/broken'!r}, sep=',')\n"
            )
            script.write_text(
                "import pandas as pd\nimport pytest\nimport requests\n"
                "from unittest.mock import patch\n"
                + cells["csv-reader"]
                + """
responses = []
original_get = requests.get

def tracked_get(*args: object, **kwargs: object) -> requests.Response:
    assert kwargs['stream'] is True
    assert kwargs['timeout'] == HTTP_TIMEOUT
    response = original_get(*args, **kwargs)
    responses.append(response)
    return response

with patch('requests.get', side_effect=tracked_get):
"""
                + indent(checks, "    ")
                + "assert len(responses) == 3\n"
                + "assert all(response.raw.closed for response in responses)\n"
            )
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            assert requests_seen == [
                ("/catalogue", "Generator-Test/1"),
                ("/selected", "Notebook-Test/1"),
                ("/missing", "Notebook-Test/1"),
                ("/broken", "Notebook-Test/1"),
            ]
            r_code = (config.temp_prefix / entry["r"]).read_text()
            assert 'USER_AGENT <- "R-Test/1"' in r_code
            assert 'headers = c("User-Agent" = USER_AGENT)' in r_code
        finally:
            server.shutdown()
            thread.join(timeout=5)
