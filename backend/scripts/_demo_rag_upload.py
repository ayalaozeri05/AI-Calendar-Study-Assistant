"""One-shot demo: verify OpenAPI RAG routes and upload a tiny PDF."""

from __future__ import annotations

import json
import tempfile
import urllib.request
from pathlib import Path

import requests
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

BASE = "http://127.0.0.1:8000"


def main() -> None:
    root = json.load(urllib.request.urlopen(f"{BASE}/", timeout=5))
    print("ROOT_KEYS", sorted(root))
    paths = json.load(urllib.request.urlopen(f"{BASE}/openapi.json", timeout=5))["paths"]
    rag = sorted(p for p in paths if "rag" in p)
    print("OPENAPI_RAG", rag)

    tmp = Path(tempfile.mkdtemp()) / "OperatingSystems.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    commands = [
        "BT",
        "/F1 12 Tf",
        "50 720 Td",
        "(Processes Threads Synchronization Deadlocks) Tj",
        "ET",
    ]
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("latin-1"))
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    page[NameObject("/Contents")] = stream
    with tmp.open("wb") as fh:
        writer.write(fh)

    with tmp.open("rb") as fh:
        resp = requests.post(
            f"{BASE}/rag/upload",
            data={"title": "Operating Systems"},
            files={"file": ("OperatingSystems.pdf", fh, "application/pdf")},
            timeout=180,
        )
    print("UPLOAD_STATUS", resp.status_code)
    print("UPLOAD_BODY", resp.text[:1000])
    if resp.ok:
        status = requests.get(f"{BASE}/rag/status", timeout=15)
        print("STATUS", status.status_code, status.text)


if __name__ == "__main__":
    main()
