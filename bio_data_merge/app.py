"""Application Module."""
from bio_data_merge.utils.parser import parser
import asyncio

def run() -> None:
    """Run the app."""
    try:
        asyncio.run(parser.start())
    except KeyboardInterrupt:
        parser.cleanup()

   



