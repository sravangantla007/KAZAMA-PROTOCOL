"""python -m app.modules.ingestion --mock"""
from __future__ import annotations
import asyncio
import json
import sys

async def main():
    mock = "--mock" in sys.argv
    from app.modules.ingestion import ingest
    from app.contracts.raw import UploadedFile
    result = await ingest(
        query="What should I verify before applying for the NMES scholarship?",
        urls=[],
        files=[],
        mock_mode=mock,
    )
    print(f"Mode: {result.mode}")
    print(f"Sources ({len(result.sources)}):")
    for src in result.sources:
        print(f"  {src.source_id} | {src.source_type:15} | {str(src.published_date):12} | {src.url_or_filename[:60]}")
    if result.issues:
        print(f"Issues ({len(result.issues)}):")
        for issue in result.issues:
            print(f"  [{issue.code}] {issue.target}: {issue.message}")


asyncio.run(main())
